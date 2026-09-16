import calendar
from collections import defaultdict
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db, Transaction, Budget, User
from ..auth import current_user
from ..schemas import BudgetIn
from ..ml import analytics as A
from ..ml.dataset import EXPENSE_CATEGORIES
from .transactions import ser
from ..services import cached

router = APIRouter(prefix="/api", tags=["analytics"])
FIXED = {"Rent", "Bills", "Education"}


def _load(db, user):
    txns = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    return txns, budgets


def _prev_month(d):
    first = d.replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    txns, budgets = _load(db, user)
    cur, prev = A.month_key(today), A.month_key(_prev_month(today))

    def totals(mk):
        inc = sum(t.amount for t in txns if t.type == "income" and A.month_key(t.date) == mk)
        exp = sum(t.amount for t in txns if t.type == "expense" and A.month_key(t.date) == mk)
        return inc, exp

    ci, ce = totals(cur)
    pi, pe = totals(prev)
    # spend to the same day last month, so the comparison is fair mid-month
    prev_same_day = sum(t.amount for t in txns if t.type == "expense" and A.month_key(t.date) == prev
                        and t.date.day <= today.day)

    months, m = [], today.replace(day=1)
    for _ in range(6):
        months.append(A.month_key(m))
        m = _prev_month(m)
    months.reverse()
    cash = [{"month": mk, "income": round(totals(mk)[0], 2), "expense": round(totals(mk)[1], 2)} for mk in months]

    cats = defaultdict(float)
    for t in txns:
        if t.type == "expense" and A.month_key(t.date) == cur:
            cats[t.category] += t.amount

    days = calendar.monthrange(today.year, today.month)[1]
    pdays = calendar.monthrange(_prev_month(today).year, _prev_month(today).month)[1]
    daily_cur, daily_prev = [0.0] * days, [0.0] * max(days, pdays)
    for t in txns:
        if t.type != "expense":
            continue
        mk = A.month_key(t.date)
        if mk == cur:
            daily_cur[t.date.day - 1] += t.amount
        elif mk == prev:
            daily_prev[t.date.day - 1] += t.amount
    cum, run_c, run_p = [], 0, 0
    for i in range(days):
        run_p += daily_prev[i] if i < pdays else 0
        if i < today.day:
            run_c += daily_cur[i]
        cum.append({"day": i + 1, "this": round(run_c, 2) if i < today.day else None, "last": round(run_p, 2)})

    recent = sorted(txns, key=lambda t: (t.date, t.id), reverse=True)[:7]
    anomalies = sorted([t for t in txns if t.is_anomaly], key=lambda t: t.date, reverse=True)[:4]
    fc = cached(user.id, ("forecast", today), lambda: A.forecast(txns, today))
    return {
        "today": today.isoformat(),
        "pace": A.pace(txns, budgets, today),
        "month": {"income": round(ci, 2), "expense": round(ce, 2),
                  "saved": round(ci - ce, 2), "savings_rate": round((ci - ce) / ci * 100, 1) if ci else None,
                  "prev_income": round(pi, 2), "prev_expense": round(pe, 2),
                  "expense_vs_same_day_last_month": round((ce - prev_same_day) / prev_same_day * 100, 1) if prev_same_day else None},
        "cashflow": cash,
        "categories": sorted([{"category": k, "amount": round(v, 2)} for k, v in cats.items()], key=lambda x: -x["amount"]),
        "cumulative": cum,
        "recent": [ser(t) for t in recent],
        "anomalies": [ser(t) for t in anomalies],
        "health": A.health_score(txns, budgets, today),
        "forecast": {"month": fc["month"], "total": fc["total"]},
        "counts": {"transactions": len(txns), "anomalies": sum(1 for t in txns if t.is_anomaly)},
    }


@router.get("/budgets")
def list_budgets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    txns, budgets = _load(db, user)
    cur = A.month_key(today)
    days = calendar.monthrange(today.year, today.month)[1]
    fc = {c["category"]: c["forecast"] for c in cached(user.id, ("forecast", today), lambda: A.forecast(txns, today))["categories"]}
    spent = defaultdict(float)
    for t in txns:
        if t.type == "expense" and A.month_key(t.date) == cur:
            spent[t.category] += t.amount
    out = []
    for b in sorted(budgets, key=lambda b: -b.monthly_limit):
        s = spent.get(b.category, 0)
        if b.category in FIXED:
            # rent and bills land once a month, so a straight-line projection would double them
            blended = max(s, fc.get(b.category, s)) if s == 0 else s
        else:
            projected = s / today.day * days
            # blend straight-line pace with the model forecast; pace alone overreacts to one big spend early on
            blended = 0.5 * projected + 0.5 * fc.get(b.category, projected) if today.day < days else s
        status = "over" if s > b.monthly_limit else ("at-risk" if blended > b.monthly_limit else "on-track")
        out.append({"id": b.id, "category": b.category, "limit": b.monthly_limit, "spent": round(s, 2),
                    "projected": round(max(blended, s), 2), "status": status,
                    "remaining": round(b.monthly_limit - s, 2),
                    "daily_allowance": round(max(b.monthly_limit - s, 0) / max(days - today.day + 1, 1), 2)})
    unbudgeted = [{"category": c, "spent": round(v, 2)} for c, v in spent.items()
                  if c not in {b.category for b in budgets}]
    return {"budgets": out, "unbudgeted": unbudgeted, "day": today.day, "days": days,
            "available_categories": [c for c in EXPENSE_CATEGORIES if c not in {b.category for b in budgets}]}


@router.put("/budgets")
def upsert_budget(body: BudgetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.category not in EXPENSE_CATEGORIES:
        raise HTTPException(422, "Pick an expense category for this budget.")
    b = db.query(Budget).filter(Budget.user_id == user.id, Budget.category == body.category).first()
    if b:
        b.monthly_limit = body.monthly_limit
    else:
        b = Budget(user_id=user.id, category=body.category, monthly_limit=body.monthly_limit)
        db.add(b)
    db.commit()
    return {"id": b.id, "category": b.category, "limit": b.monthly_limit}


@router.delete("/budgets/{budget_id}", status_code=204)
def delete_budget(budget_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(Budget, budget_id)
    if not b or b.user_id != user.id:
        raise HTTPException(404, "Budget not found.")
    db.delete(b)
    db.commit()


@router.get("/insights")
def insights(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    txns, budgets = _load(db, user)
    fc = cached(user.id, ("forecast", today), lambda: A.forecast(txns, today))
    health = A.health_score(txns, budgets, today)
    rule = A.rule_50_30_20(txns, today)
    limits = {b.category: b.monthly_limit for b in budgets}
    tips = []
    for c in fc["categories"]:
        lim = limits.get(c["category"])
        if lim and c["forecast"] > lim:
            tips.append({"tone": "warn", "title": f"{c['category']} is likely to go over budget next month",
                         "body": f"Forecast ₹{c['forecast']:,.0f} against a ₹{lim:,.0f} limit. "
                                 f"Cutting about ₹{(c['forecast'] - lim) / 4:,.0f} a week keeps it on track."})
        elif c["last"] and c["forecast"] > c["last"] * 1.15 and c["forecast"] > 1000:
            tips.append({"tone": "info", "title": f"{c['category']} spending is trending up",
                         "body": f"Last month ₹{c['last']:,.0f}, next month forecast ₹{c['forecast']:,.0f}."})
    if rule and rule["actual"]["savings"] < rule["ideal"]["savings"]:
        gap = rule["ideal"]["savings"] - rule["actual"]["savings"]
        tips.append({"tone": "warn", "title": "You're saving less than 20% of income",
                     "body": f"Moving ₹{gap:,.0f} a month from wants to savings reaches the 50/30/20 target."})
    elif rule:
        tips.append({"tone": "good", "title": "Savings are above the 20% target",
                     "body": f"You kept ₹{rule['actual']['savings']:,.0f} a month on average over the last 3 months."})
    # monthly history per category for charts
    hist = defaultdict(lambda: defaultdict(float))
    for t in txns:
        if t.type == "expense" and A.month_key(t.date) < A.month_key(today):
            hist[t.category][A.month_key(t.date)] += t.amount
    months = sorted({m for h in hist.values() for m in h})[-6:]
    return {
        "forecast": fc, "health": health, "rule_50_30_20": rule, "tips": tips[:6],
        "category_history": {"months": months,
                             "series": {c: [round(h.get(m, 0), 2) for m in months] for c, h in hist.items()}},
        "anomalies": [ser(t) for t in sorted([t for t in txns if t.is_anomaly], key=lambda t: t.date, reverse=True)],
    }


@router.get("/ml-insights")
def ml_insights(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..ml import ml_insights as MI
    from ..db import Goal
    today = date.today()
    txns, _ = _load(db, user)
    data = cached(user.id, ("ml_insights", today), lambda: MI.build(txns, today))
    goals = db.query(Goal).filter(Goal.user_id == user.id).all()
    return {**data, "goals": [{"name": g.name, "emoji": g.emoji, "remaining": round(max(g.target - g.saved, 0), 2)} for g in goals if g.saved < g.target]}
