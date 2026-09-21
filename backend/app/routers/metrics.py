import json, time
from collections import defaultdict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..db import get_db, ModelRun, Transaction, User, LoginEvent
from ..auth import current_user
from ..ml.categorizer import categorizer
from ..ml import analytics as A
from .. import metrics_store
from datetime import date
from .assistant import assistant_stats

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


def csv_benchmark():
    """Parse + clean + categorise a 500-row statement, the same steps the import endpoint runs."""
    import io, random
    import pandas as pd
    from ..ml import dataset
    rng = random.Random(7)
    lines = ["Date,Narration,Debit,Credit"]
    cats = list(dataset.TEMPLATES)
    for i in range(500):
        lines.append(f"{(i % 28) + 1:02d}/08/2026,{dataset.fill(rng.choice(dataset.TEMPLATES[rng.choice(cats)]), rng)},{rng.randint(50, 3000)},")
    raw = "\n".join(lines).encode()
    t0 = time.perf_counter()
    df = pd.read_csv(io.BytesIO(raw), dtype=str).fillna("")
    dates = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    amounts = df["Debit"].str.replace(",", "").astype(float)
    categorizer.predict(df["Narration"].tolist())
    ms = (time.perf_counter() - t0) * 1000
    return {"rows": 500, "ms": round(ms, 1), "valid_dates": int(dates.notna().sum()), "total": float(amounts.sum())}
BENCH = {}


def run_out(r):
    return {"id": r.id, "ts": r.ts.isoformat() + "Z", "trigger": r.trigger, "n_train": r.n_train, "n_test": r.n_test,
            "n_corrections": r.n_corrections, "accuracy": round(r.accuracy * 100, 2), "f1_macro": round(r.f1_macro, 4),
            "train_ms": round(r.train_ms, 1), **json.loads(r.details)}


@router.get("/live")
def live(window: int = Query(300, ge=60, le=3600), user: User = Depends(current_user)):
    bucket = 5 if window <= 300 else (15 if window <= 900 else 60)
    return metrics_store.snapshot(window, bucket)


@router.get("/models")
def models(user: User = Depends(current_user), db: Session = Depends(get_db)):
    runs = db.query(ModelRun).order_by(ModelRun.id.desc()).limit(12).all()
    if "csv_500" not in BENCH:
        BENCH["csv_500"] = csv_benchmark()
    txns = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    exp = [t for t in txns if t.type == "expense" and not t.user_corrected]
    bins = [0] * 10
    for t in exp:
        bins[min(int(t.confidence * 10), 9)] += 1
    from ..services import cached
    fc = cached(user.id, ("forecast", date.today()), lambda: A.forecast(txns, date.today()))
    corrections = db.query(Transaction).filter(Transaction.user_corrected.is_(True)).count()
    sample = [t.description for t in exp[:20]] or ["UPI/SWIGGY/VELLORE/123456"]
    t0 = time.perf_counter()
    for d in sample:
        categorizer.predict([d])
    inference_ms = (time.perf_counter() - t0) * 1000 / len(sample)
    return {
        "latest": run_out(runs[0]) if runs else None,
        "history": [run_out(r) | {"confusion": None} for r in reversed(runs)],
        "confidence_histogram": [{"bucket": f"{i * 10}–{(i + 1) * 10}%", "count": c} for i, c in enumerate(bins)],
        "inference_ms": round(inference_ms, 3),
        "avg_confidence": round(sum(t.confidence for t in exp) / len(exp) * 100, 2) if exp else None,
        "pending_corrections": corrections,
        "user": {"transactions": len(txns), "anomalies": sum(t.is_anomaly for t in txns),
                 "forecast_backtest_mape": fc["backtest_mape"], "forecast_months": len(fc["history"])},
        "benchmarks": BENCH,
        "assistant": assistant_stats(db),
    }


@router.post("/retrain")
def retrain(user: User = Depends(current_user), db: Session = Depends(get_db)):
    corrections = [(t.description, t.category) for t in
                   db.query(Transaction).filter(Transaction.user_corrected.is_(True), Transaction.type == "expense").all()]
    rep = categorizer.train(corrections)
    run = ModelRun(trigger="retrain", **rep)
    db.add(run)
    db.commit()
    return run_out(run)


@router.post("/probe")
def probe(user: User = Depends(current_user)):
    """Cheap endpoint the load test uses alongside real ones."""
    t0 = time.perf_counter()
    categorizer.predict(["UPI/SWIGGY/VELLORE/123456"])
    return {"inference_ms": round((time.perf_counter() - t0) * 1000, 3)}


@router.get("/users")
def users(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Aggregate usage only; no other user's name or email is ever returned."""
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from ..seed import DEMO_EMAIL
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    demo_id = db.query(User.id).filter(User.email == DEMO_EMAIL).scalar()
    real = db.query(User).filter(User.email != DEMO_EMAIL)
    events = db.query(LoginEvent)
    days = 14
    start = today - timedelta(days=days - 1)
    logins = defaultdict(int)
    for (ts,) in events.filter(LoginEvent.ts >= start).with_entities(LoginEvent.ts).all():
        logins[ts.date()] += 1
    signups = defaultdict(int)
    for (ts,) in real.filter(User.created_at >= start).with_entities(User.created_at).all():
        signups[ts.date()] += 1
    series = [{"day": (start + timedelta(days=i)).date().isoformat(), "logins": logins[(start + timedelta(days=i)).date()],
               "signups": signups[(start + timedelta(days=i)).date()]} for i in range(days)]
    return {
        "registered_users": real.count(),
        "new_today": real.filter(User.created_at >= today).count(),
        "active_now": db.query(User).filter(User.last_seen >= now - timedelta(minutes=5)).count(),
        "active_today": db.query(User).filter(User.last_seen >= today).count(),
        "active_7d": db.query(User).filter(User.last_seen >= now - timedelta(days=7)).count(),
        "total_logins": events.count(),
        "logins_today": events.filter(LoginEvent.ts >= today).count(),
        "demo_sessions": events.filter(LoginEvent.user_id == demo_id).count() if demo_id else 0,
        "active_window_minutes": 5,
        "series": series,
    }
