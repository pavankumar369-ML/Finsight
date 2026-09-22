"""Tiny shared module so routers can check startup readiness without importing main.py (avoids circular imports)."""
from fastapi import HTTPException

READY = False   # flipped true by main.py once the model is trained and the demo account is seeded
WARM_UP_ERROR = False   # set if the background warm-up raised; reported by /api/health


def require_ready():
    if not READY:
        raise HTTPException(503, "FinSight is still starting up (training its ML model). Try again in a few seconds.",
                            headers={"Retry-After": "5"})
