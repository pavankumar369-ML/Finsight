from datetime import date
import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db, Transaction, Budget, Goal, ChatMessage, User
from ..auth import current_user
from ..schemas import ChatIn
from .. import assistant as AI
from ..ml import analytics as A
from ..services import cached

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def msg_out(m):
    return {"id": m.id, "role": m.role, "content": m.content, "mode": m.mode, "ms": round(m.ms, 1) if m.ms else None,
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
    ctx = AI.build_context(txns, budgets, goals, fc, rec, today)
    hist = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(6).all()[::-1]
    text, mode, ms, err = AI.reply(body.message.strip(), ctx, hist)
    q = ChatMessage(user_id=user.id, role="user", content=body.message.strip())
    a = ChatMessage(user_id=user.id, role="assistant", content=text, mode=mode, ms=ms)
    db.add_all([q, a])
    db.commit()
    return {"user": msg_out(q), "assistant": msg_out(a), "fallback_reason": err}


def assistant_stats(db):
    rows = db.query(ChatMessage.ms, ChatMessage.mode).filter(ChatMessage.role == "assistant", ChatMessage.ms.isnot(None)) \
        .order_by(ChatMessage.id.desc()).limit(200).all()
    if not rows:
        return {"count": 0, **AI.status()}
    ms = np.array([r[0] for r in rows])
    llm = np.array([r[0] for r in rows if r[1] == "llm"])
    return {"count": len(rows), "avg_ms": round(float(ms.mean()), 1), "p95_ms": round(float(np.percentile(ms, 95)), 1),
            "llm_count": len(llm), "llm_avg_ms": round(float(llm.mean()), 1) if len(llm) else None, **AI.status()}
