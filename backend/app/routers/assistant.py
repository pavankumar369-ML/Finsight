from datetime import date
import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db, Transaction, Budget, Goal, ChatMessage, User
from ..auth import current_user
from ..schemas import ChatIn
from .. import assistant_engine as AI
from ..ml import analytics as A
from ..services import cached

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def msg_out(m):
    return {"id": m.id, "role": m.role, "content": m.content, "intent": m.mode, "ms": round(m.ms, 2) if m.ms is not None else None,
            "ts": m.ts.isoformat() + "Z"}


@router.get("/status")
def status(user: User = Depends(current_user)):
    return AI.status()


@router.get("/history")
def history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(60).all()
    return {"messages": [msg_out(m) for m in reversed(rows)], **AI.status()}


@router.delete("/history", status_code=204)
def clear(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(ChatMessage).filter(ChatMessage.user_id == user.id).delete()
    db.commit()


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    txns = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    goals = db.query(Goal).filter(Goal.user_id == user.id).all()
    fc = cached(user.id, ("forecast", today), lambda: A.forecast(txns, today))
    rec = cached(user.id, ("recurring", today), lambda: A.detect_recurring(txns, today))
    health = A.health_score(txns, budgets, today)
    r = AI.answer(body.message, AI.Ctx(txns, budgets, goals, fc, rec, health, today))
    q = ChatMessage(user_id=user.id, role="user", content=body.message.strip())
    a = ChatMessage(user_id=user.id, role="assistant", content=r["text"], mode=r["intent_label"][:20], ms=r["ms"])
    db.add_all([q, a])
    db.commit()
    return {"user": msg_out(q), "assistant": msg_out(a), "suggestions": r["suggestions"], "intent": r["intent"],
            "confidence": r["confidence"], "entities": r["entities"]}


def assistant_stats(db):
    rows = [r[0] for r in db.query(ChatMessage.ms).filter(ChatMessage.role == "assistant", ChatMessage.ms.isnot(None))
            .order_by(ChatMessage.id.desc()).limit(500).all()]
    base = AI.status()
    if not rows:
        return {"count": 0, **base}
    ms = np.array(rows)
    return {"count": len(rows), "avg_ms": round(float(ms.mean()), 2), "p95_ms": round(float(np.percentile(ms, 95)), 2), **base}
