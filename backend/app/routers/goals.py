import math
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db, Goal, Transaction, User
from ..auth import current_user
from ..schemas import GoalIn, GoalPatch, ContributeIn
from ..ml import analytics as A
from ..services import cached

router = APIRouter(prefix="/api/goals", tags=["goals"])


def _months_between(a: date, b: date):
    return (b.year - a.year) * 12 + (b.month - a.month) + (b.day - a.day) / 30


def goal_out(g: Goal, monthly_savings: float, n_goals: int, today: date):
    remaining = max(g.target - g.saved, 0)
    share = monthly_savings / max(n_goals, 1) if monthly_savings > 0 else 0   # savings split across active goals
    months_needed = math.ceil(remaining / share) if share > 0 and remaining > 0 else (0 if remaining == 0 else None)
    projected = None
    if months_needed is not None:
        y, m = today.year, today.month + months_needed
        y += (m - 1) // 12
        m = (m - 1) % 12 + 1
        projected = date(y, m, min(today.day, 28)).isoformat()
    required, status = None, "no-deadline"
    if remaining == 0:
        status = "done"
    elif g.deadline:
        months_left = _months_between(today, g.deadline)
        required = round(remaining / months_left, 2) if months_left > 0 else remaining
        status = "overdue" if months_left <= 0 else ("on-track" if share >= required else "behind")
    return {"id": g.id, "name": g.name, "emoji": g.emoji, "target": g.target, "saved": round(g.saved, 2),
            "remaining": round(remaining, 2), "progress": round(min(g.saved / g.target, 1), 4),
            "deadline": g.deadline.isoformat() if g.deadline else None, "status": status,
            "required_monthly": required, "suggested_monthly": round(share, 2),
            "months_needed": months_needed, "projected_date": projected}


def _own(db, user, gid):
    g = db.get(Goal, gid)
    if not g or g.user_id != user.id:
        raise HTTPException(404, "Goal not found.")
    return g


@router.get("")
def list_goals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    goals = db.query(Goal).filter(Goal.user_id == user.id).order_by(Goal.created_at).all()
    txns = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    ms = cached(user.id, ("avg_savings", today), lambda: A.avg_monthly_savings(txns, today))
    active = sum(1 for g in goals if g.saved < g.target)
    return {"monthly_savings": round(ms, 2), "goals": [goal_out(g, ms, active, today) for g in goals],
            "total_target": round(sum(g.target for g in goals), 2), "total_saved": round(sum(g.saved for g in goals), 2)}


@router.post("", status_code=201)
def create_goal(body: GoalIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.query(Goal).filter(Goal.user_id == user.id).count() >= 20:
        raise HTTPException(422, "You can have up to 20 goals.")
    g = Goal(user_id=user.id, **body.model_dump())
    db.add(g)
    db.commit()
    return {"id": g.id}


@router.patch("/{gid}")
def update_goal(gid: int, body: GoalPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _own(db, user, gid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(g, k, v)
    db.commit()
    return {"id": g.id}


@router.post("/{gid}/contribute")
def contribute(gid: int, body: ContributeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _own(db, user, gid)
    new = g.saved + body.amount
    if new < 0:
        raise HTTPException(422, f"You can withdraw at most ₹{g.saved:,.0f} from this goal.")
    g.saved = round(new, 2)
    db.commit()
    return {"id": g.id, "saved": g.saved, "completed": g.saved >= g.target}


@router.delete("/{gid}", status_code=204)
def delete_goal(gid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, user, gid))
    db.commit()
