from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db, Transaction, Budget, Goal, User
from ..auth import current_user
from ..ml import analytics as A
from ..services import cached
from .analytics import list_budgets

router = APIRouter(prefix="/api", tags=["notifications"])


def recurring_for(user, txns, today):
    return cached(user.id, ("recurring", today), lambda: A.detect_recurring(txns, today))


@router.get("/recurring")
def recurring(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    txns = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    items = recurring_for(user, txns, today)
    return {"items": items, "monthly_total": round(sum(i["amount"] for i in items), 2),
            "due_7_days": sum(1 for i in items if 0 <= i["days_until"] <= 7)}


@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Generated from live data each time, so they never go stale. The client tracks which ids were seen."""
    today = date.today()
    txns = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    out = []
    for b in list_budgets(user, db)["budgets"]:
        mk = A.month_key(today)
        if b["status"] == "over":
            out.append({"id": f"budget-over-{b['category']}-{mk}", "tone": "bad", "link": "/budgets",
                        "title": f"{b['category']} budget exceeded", "body": f"Spent ₹{b['spent']:,.0f} of ₹{b['limit']:,.0f} this month."})
        elif b["status"] == "at-risk":
            out.append({"id": f"budget-risk-{b['category']}-{mk}", "tone": "warn", "link": "/budgets",
                        "title": f"{b['category']} may go over budget", "body": f"Heading for ₹{b['projected']:,.0f} against ₹{b['limit']:,.0f}."})
    for r in recurring_for(user, txns, today):
        if 0 <= r["days_until"] <= 7:
            when = "today" if r["days_until"] == 0 else ("tomorrow" if r["days_until"] == 1 else f"in {r['days_until']} days")
            out.append({"id": f"bill-{r['merchant']}-{r['next_due']}", "tone": "info", "link": "/budgets",
                        "title": f"{r['merchant']} due {when}", "body": f"Usually about ₹{r['amount']:,.0f}."})
    for t in sorted([t for t in txns if t.is_anomaly], key=lambda t: t.date, reverse=True)[:3]:
        if (today - t.date).days <= 45:
            out.append({"id": f"anomaly-{t.id}", "tone": "bad", "link": "/transactions?anomaly=1",
                        "title": "Unusual spend flagged", "body": f"₹{t.amount:,.0f} at {t.description[:40]}: {t.anomaly_reason}."})
    for g in db.query(Goal).filter(Goal.user_id == user.id).all():
        pct = g.saved / g.target if g.target else 0
        for mark in (1.0, 0.75, 0.5):
            if pct >= mark:
                label = "reached" if mark == 1 else f"{int(mark * 100)}% of the way"
                out.append({"id": f"goal-{g.id}-{int(mark * 100)}", "tone": "good", "link": "/goals",
                            "title": f"{g.emoji} {g.name}: {label}", "body": f"₹{g.saved:,.0f} saved of ₹{g.target:,.0f}."})
                break
    return {"items": out}
