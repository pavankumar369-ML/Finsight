import asyncio, logging, os, time
from collections import defaultdict, deque
from fastapi.responses import JSONResponse
from .auth import SECRET
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db, SessionLocal, ModelRun, Transaction, engine, DB_URL
from .ml.categorizer import categorizer
from . import metrics_store, state, artifacts
from .routers import auth, transactions, analytics, metrics, goals, notifications, assistant
from .seed import ensure_demo


async def _flusher():
    while True:
        await asyncio.sleep(5)
        await asyncio.to_thread(metrics_store.flush)


def _record_model_run(db, trigger, report):
    """Store a ModelRun only when the metrics differ from the latest one, so restarts that load the
    same pre-trained model don't pile identical rows into the training-run history chart."""
    last = db.query(ModelRun).order_by(ModelRun.id.desc()).first()
    if last and last.n_train == report["n_train"] and abs(last.accuracy - report["accuracy"]) < 1e-9 \
            and last.n_corrections == report["n_corrections"]:
        return
    db.add(ModelRun(trigger=trigger, **report))
    db.commit()


def _warm_up_sync():
    """Loads (or, if no pre-built artifact exists, trains) the ML models in a background thread,
    after the server is already accepting requests. Every stage is logged with its timing, and the
    whole thing is wrapped in try/except so a failure is visible in the logs instead of silently
    leaving the app 'not ready' forever."""
    log = logging.getLogger("uvicorn.error")
    t0 = time.time()
    stage = lambda msg: log.info("FinSight warm-up: %s (+%.1fs)", msg, time.time() - t0)
    try:
        db = SessionLocal()
        try:
            from .services import training_corrections
            corrections = training_corrections(db)
            loaded = artifacts.load_joblib("categorizer")
            if loaded:
                report = categorizer.load(loaded[0], loaded[1]["report"])
                stage("categoriser loaded from pre-built artifact")
            else:
                report = categorizer.train(corrections)
                stage("categoriser trained (no artifact found)")
            _record_model_run(db, "startup", report)
            demo = ensure_demo(db)                    # instant if the demo account already exists
            stage("demo account ready")
        finally:
            db.close()
        from . import assistant_engine
        assistant_engine.get_intent_model()           # loads the pre-built artifact, or trains if missing
        stage("assistant intent model ready")
        state.READY = True
        stage("READY: all ML features available")

        if loaded and corrections:
            # the pre-built model has no user corrections; fold them in now, as startup always did
            report = categorizer.train(corrections)
            db = SessionLocal()
            try:
                _record_model_run(db, "startup", report)
            finally:
                db.close()
            stage(f"categoriser retrained with {len(corrections)} user corrections")
        if not metrics.BENCH.get("forecast"):
            from .ml import benchmarks
            metrics.BENCH.update(benchmarks.run_all())
            stage("benchmarks computed (no artifact found)")
        # warm the demo account's caches (read from the database cache, or computed and stored once)
        db = SessionLocal()
        try:
            from .routers.analytics import dashboard, list_budgets, insights
            demo = ensure_demo(db)
            for fn in (dashboard, list_budgets, insights):
                fn(demo, db)
        finally:
            db.close()
        stage("demo dashboard cache warm")
    except Exception:
        log.exception("FinSight warm-up FAILED after %.1fs; ML-dependent actions will keep returning 503", time.time() - t0)
        state.WARM_UP_ERROR = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    log = logging.getLogger("uvicorn.error")
    log.info("FinSight startup: connecting to database (%s)...",
             "postgres" if not DB_URL.startswith("sqlite") else "sqlite")
    t0 = time.time()
    init_db()                    # fast: create/alter tables only
    log.info("FinSight startup: database ready in %.1fs", time.time() - t0)
    metrics_store.load_history()
    bench = artifacts.load_json("benchmarks")    # tiny JSON read: Metrics benchmarks are available immediately
    if bench:
        metrics.BENCH.update(bench)
    task = asyncio.create_task(_flusher())
    warm = asyncio.create_task(asyncio.to_thread(_warm_up_sync))
    yield
    task.cancel()
    warm.cancel()
    metrics_store.flush()


app = FastAPI(title="FinSight API", version="3.8.1", lifespan=lifespan)
ORIGINS = [o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_origin_regex=os.getenv("ALLOWED_ORIGIN_REGEX") or None,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"], max_age=600)
if SECRET.startswith("dev-secret") and os.getenv("RENDER"):
    logging.getLogger("uvicorn.error").warning("FINSIGHT_SECRET is the development default. Set a random value in Render.")


_attempts = defaultdict(deque)
AUTH_LIMIT, AUTH_WINDOW = 10, 300   # 10 sign-in/register attempts per 5 minutes per IP
_hits = defaultdict(deque)
API_LIMIT, API_WINDOW = int(os.getenv("API_RATE_LIMIT", "300")), 60   # requests per minute per IP, for all API calls


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    status = 500
    try:
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        if request.url.path.startswith("/api/") and request.url.path != "/api/health":
            h, now = _hits[ip], time.time()
            while h and h[0] < now - API_WINDOW:
                h.popleft()
            if len(h) >= API_LIMIT:
                status = 429
                return JSONResponse({"detail": "Too many requests. Slow down for a minute and try again."}, status_code=429,
                                    headers={"Retry-After": "60"})
            h.append(now)
        if request.method == "POST" and request.url.path in ("/api/auth/login", "/api/auth/register", "/api/auth/change-password"):
            q, now = _attempts[ip], time.time()
            while q and q[0] < now - AUTH_WINDOW:
                q.popleft()
            if len(q) >= AUTH_LIMIT:
                status = 429
                return JSONResponse({"detail": "Too many sign-in attempts. Wait a few minutes and try again."}, status_code=429,
                                    headers={"Retry-After": str(int(AUTH_WINDOW - (now - q[0])))})
            q.append(now)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        status = response.status_code
        return response
    finally:
        ms = (time.perf_counter() - t0) * 1000
        metrics_store.record(request.method, request.url.path, status, ms)


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    return {"ok": True, "model_ready": categorizer.pipe is not None, "ready": state.READY,
            "warm_up_error": state.WARM_UP_ERROR, "version": app.version,
            "database": "postgres" if not str(engine.url).startswith("sqlite") else "sqlite"}


@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"name": "FinSight API", "version": app.version, "docs": "/docs", "health": "/api/health"}


for r in (auth.router, transactions.router, analytics.router, metrics.router, goals.router, notifications.router, assistant.router):
    app.include_router(r)
