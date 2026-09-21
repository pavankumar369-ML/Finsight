"""In-process request metrics: a ring buffer for live charts, flushed to SQLite for history."""
import threading, time
from collections import deque
from datetime import datetime, timedelta
import numpy as np
from .db import SessionLocal, RequestLog

STARTED_AT = time.time()
_buf = deque(maxlen=50000)     # (epoch, method, path, status, ms)
_pending = []
_lock = threading.Lock()
SKIP_PREFIXES = ("/api/metrics/live", "/api/metrics/models", "/api/metrics/users")   # the Metrics page's own polling


def normalise(path: str) -> str:
    parts = [("{id}" if p.isdigit() else p) for p in path.split("/")]
    return "/".join(parts)


def record(method, path, status, ms):
    if not path.startswith("/api") or path.startswith(SKIP_PREFIXES):
        return
    item = (time.time(), method, normalise(path), status, ms)
    with _lock:
        _buf.append(item)
        _pending.append(item)


def flush():
    with _lock:
        items = list(_pending)
        _pending.clear()
    if not items:
        return
    db = SessionLocal()
    try:
        db.bulk_save_objects([RequestLog(ts=datetime.utcfromtimestamp(e), method=m, path=p, status=s, ms=ms)
                              for e, m, p, s, ms in items])
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def load_history(hours=24):
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(hours=hours)
        rows = db.query(RequestLog).filter(RequestLog.ts >= since).order_by(RequestLog.ts).all()
        with _lock:
            for r in rows:
                _buf.append(((r.ts - datetime(1970, 1, 1)).total_seconds(), r.method, r.path, r.status, r.ms))
    finally:
        db.close()


def _pct(arr, q):
    return round(float(np.percentile(arr, q)), 2) if len(arr) else 0.0


def snapshot(window_s=300, bucket_s=5):
    now = time.time()
    with _lock:
        items = [i for i in _buf if i[0] >= now - window_s]
        total_all = len(_buf)
    ms = np.array([i[4] for i in items]) if items else np.array([])
    n_buckets = window_s // bucket_s
    series = []
    for b in range(n_buckets):
        start = now - window_s + b * bucket_s
        chunk = [i[4] for i in items if start <= i[0] < start + bucket_s]
        series.append({"t": int((start + bucket_s) * 1000), "count": len(chunk),
                       "avg": round(float(np.mean(chunk)), 2) if chunk else None,
                       "p95": round(float(np.percentile(chunk, 95)), 2) if chunk else None})
    endpoints = {}
    for _, m, p, s, v in items:
        e = endpoints.setdefault(f"{m} {p}", {"endpoint": f"{m} {p}", "ms": [], "errors": 0})
        e["ms"].append(v)
        if s >= 400:
            e["errors"] += 1
    ep = sorted(({"endpoint": k, "count": len(v["ms"]), "avg": round(float(np.mean(v["ms"])), 2),
                  "p95": _pct(v["ms"], 95), "errors": v["errors"]} for k, v in endpoints.items()),
                key=lambda x: -x["count"])[:10]
    status = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
    for i in items:
        status[f"{i[3] // 100}xx"] = status.get(f"{i[3] // 100}xx", 0) + 1
    dash = [i[4] for i in items if i[2] == "/api/dashboard"]
    return {
        "window_s": window_s, "bucket_s": bucket_s, "uptime_s": int(now - STARTED_AT),
        "requests": len(items), "requests_all_time": total_all,
        "rpm": round(len(items) / (window_s / 60), 2),
        "p50": _pct(ms, 50), "p95": _pct(ms, 95), "p99": _pct(ms, 99),
        "avg": round(float(ms.mean()), 2) if len(ms) else 0.0,
        "dashboard_avg": round(float(np.mean(dash)), 2) if dash else None,
        "dashboard_p95": _pct(dash, 95) if dash else None,
        "error_rate": round(sum(1 for i in items if i[3] >= 500) / len(items) * 100, 2) if items else 0.0,
        "status": status, "series": series, "endpoints": ep,
    }
