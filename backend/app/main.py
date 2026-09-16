import asyncio, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db, SessionLocal, ModelRun, Transaction
from .ml.categorizer import categorizer
from .ml import benchmarks
from . import metrics_store
from .routers import auth, transactions, analytics, metrics
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
        corrections = [(t.description, t.category) for t in
                       db.query(Transaction).filter(Transaction.user_corrected.is_(True), Transaction.type == "expense")]
        db.add(ModelRun(trigger="startup", **categorizer.train(corrections)))
        db.commit()
        ensure_demo(db)
    finally:
        db.close()
    metrics.BENCH.update(benchmarks.run_all())
    metrics_store.load_history()
    task = asyncio.create_task(_flusher())
    yield
    task.cancel()
    metrics_store.flush()


app = FastAPI(title="FinSight API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        ms = (time.perf_counter() - t0) * 1000
        metrics_store.record(request.method, request.url.path, status, ms)


@app.get("/api/health")
def health():
    return {"ok": True, "model_ready": categorizer.pipe is not None}


for r in (auth.router, transactions.router, analytics.router, metrics.router):
    app.include_router(r)
