import threading
from collections import defaultdict
from .db import Transaction
from .ml.analytics import detect_anomalies

# Per-user data version. Any write bumps it, which invalidates cached model outputs for that user.
_versions = defaultdict(int)
_cache = {}
_lock = threading.Lock()


def bump(user_id):
    with _lock:
        _versions[user_id] += 1
        for k in [k for k in _cache if k[0] == user_id]:
            del _cache[k]


def cached(user_id, key, fn):
    """Memoise expensive per-user computations (Holt-Winters fits) until that user's data changes."""
    with _lock:
        ck = (user_id, _versions[user_id], key)
        if ck in _cache:
            return _cache[ck]
    value = fn()
    with _lock:
        if len(_cache) > 2000:
            _cache.clear()
        _cache[(user_id, _versions[user_id], key)] = value
    return value


def refresh_anomalies(db, user_id):
    txns = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    flagged = detect_anomalies(txns)
    for t in txns:
        reason = flagged.get(t.id)
        t.is_anomaly = reason is not None
        t.anomaly_reason = reason
    db.commit()
    bump(user_id)
    return len(flagged)
