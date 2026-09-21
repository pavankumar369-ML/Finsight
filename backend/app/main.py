import asyncio, logging, os, time
from collections import defaultdict, deque
from fastapi.responses import JSONResponse
from .auth import SECRET
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db, SessionLocal, ModelRun, Transaction, engine
from .ml.categorizer import categorizer
from .ml import benchmarks
from . import metrics_store
from .routers import auth, transactions, analytics, metrics, goals, notifications, assistant
from .seed import ensure_demo


async def _flusher():
    while True:
        await asyncio.sleep(5)
        await asyncio.to_thread(metrics_store.flush)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        from .services import training_corrections
        db.add(ModelRun(trigger="startup", **categorizer.train(training_corrections(db))))
        db.commit()
        demo = ensure_demo(db)
        # warm the per-user cache so the first visitor (e.g. a recruiter waking a sleeping server) gets a fast dashboard
        from .routers.analytics import dashboard, list_budgets, insights
        for fn in (dashboard, list_budgets, insights):
            fn(demo, db)
    finally:
        db.close()
    metrics.BENCH.update(benchmarks.run_all())
    metrics_store.load_history()
    task = asyncio.create_task(_flusher())
    yield
    task.cancel()
    metrics_store.flush()


app = FastAPI(title="FinSight API", version="3.5.0", lifespan=lifespan)
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


@app.get("/api/health")
def health():
    return {"ok": True, "model_ready": categorizer.pipe is not None, "version": app.version,
            "database": "postgres" if not str(engine.url).startswith("sqlite") else "sqlite"}


@app.get("/")
def root():
    return {"name": "FinSight API", "version": app.version, "docs": "/docs", "health": "/api/health"}


for r in (auth.router, transactions.router, analytics.router, metrics.router, goals.router, notifications.router, assistant.router):
    app.include_router(r)
