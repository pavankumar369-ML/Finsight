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


MAX_CORRECTIONS_PER_USER = 50
MIN_TXNS_FOR_TRUST = 10


def training_corrections(db):
    """Category corrections that are safe to learn from.
    Guards against data poisoning: the shared demo account is excluded (anyone can edit it), only accounts
    with real data count, and each account contributes at most its 50 most recent corrections."""
    from sqlalchemy import func
    from .db import User
    from .seed import DEMO_EMAIL
    demo_id = db.query(User.id).filter(User.email == DEMO_EMAIL).scalar()
    trusted = [uid for uid, n in db.query(Transaction.user_id, func.count(Transaction.id)).group_by(Transaction.user_id).all()
               if n >= MIN_TXNS_FOR_TRUST and uid != demo_id]
    out = []
    for uid in trusted:
        rows = (db.query(Transaction).filter(Transaction.user_id == uid, Transaction.user_corrected.is_(True), Transaction.type == "expense")
                .order_by(Transaction.id.desc()).limit(MAX_CORRECTIONS_PER_USER).all())
        out += [(t.description, t.category) for t in rows]
    return out


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
