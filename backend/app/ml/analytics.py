"""Forecasting, anomaly detection, financial health score and budget pace."""
import calendar, math, warnings
from collections import defaultdict
from datetime import date
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

warnings.filterwarnings("ignore")


def month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def monthly_frame(txns):
    if not txns:
        return pd.DataFrame(columns=["month", "type", "category", "amount"])
    return pd.DataFrame([{"month": month_key(t.date), "type": t.type, "category": t.category,
                          "amount": t.amount} for t in txns])


def _forecast_series(values):
    """values: monthly totals oldest->newest (complete months). Returns (forecast, method)."""
    vals = [float(v) for v in values]
    if len(vals) == 0:
        return 0.0, "no-data"
    if len(vals) < 4:
        return float(np.mean(vals)), "mean"
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(np.array(vals), trend="add", damped_trend=True,
                                     initialization_method="estimated").fit()
        f = float(model.forecast(1)[0])
        # guard against wild extrapolation on short histories
        lo, hi = min(vals) * 0.5, max(vals) * 1.5
        return max(lo, min(hi, f)), "holt-winters"
    except Exception:
        w = np.arange(1, len(vals[-3:]) + 1)
        return float(np.average(vals[-3:], weights=w)), "weighted-mean"


def forecast(txns, today: date):
    """Forecast next month's spend per category using complete past months."""
    # anomalies are one-off events; leaving them in would drag every future forecast upward
    df = monthly_frame([t for t in txns if t.type == "expense" and not t.is_anomaly])
    current = month_key(today)
    if df.empty:
        return {"month": None, "total": 0, "categories": [], "history": [], "backtest_mape": None}
    past = df[df["month"] < current]
    months = sorted(past["month"].unique())
    pivot = past.pivot_table(index="month", columns="category", values="amount", aggfunc="sum").reindex(months).fillna(0)
    cats = []
    for cat in pivot.columns:
        f, method = _forecast_series(pivot[cat].tolist())
        cats.append({"category": cat, "forecast": round(f, 2), "method": method,
                     "last": round(float(pivot[cat].iloc[-1]), 2) if len(pivot) else 0})
    cats.sort(key=lambda c: -c["forecast"])
    totals = pivot.sum(axis=1).tolist()
    total_f, _ = _forecast_series(totals)
    # backtest: predict the last complete month from the months before it
    mape = None
    if len(totals) >= 5:
        errs = []
        for k in range(max(4, len(totals) - 3), len(totals)):
            pred, _ = _forecast_series(totals[:k])
            if totals[k] > 0:
                errs.append(abs(totals[k] - pred) / totals[k])
        mape = round(float(np.mean(errs)) * 100, 2) if errs else None
    ny, nm = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return {"month": f"{ny}-{nm:02d}", "total": round(total_f, 2), "categories": cats,
            "history": [{"month": m, "total": round(v, 2)} for m, v in zip(months, totals)],
            "backtest_mape": mape}


def detect_anomalies(txns):
    """Isolation Forest over (log amount, category, weekday, amount vs category median).
    Returns {txn_id: reason} for flagged expenses."""
    exp = [t for t in txns if t.type == "expense" and t.category not in ("Rent",)]
    if len(exp) < 30:
        return {}
    cats = sorted({t.category for t in exp})
    cidx = {c: i for i, c in enumerate(cats)}
    by_cat = defaultdict(list)
    for t in exp:
        by_cat[t.category].append(t.amount)
    med = {c: float(np.median(v)) for c, v in by_cat.items()}
    X = np.array([[math.log1p(t.amount), cidx[t.category], t.date.weekday(),
                   math.log1p(t.amount / max(med[t.category], 1))] for t in exp])
    iso = IsolationForest(n_estimators=200, contamination=0.03, random_state=42).fit(X)
    flags = iso.predict(X)
    out = {}
    for t, f in zip(exp, flags):
        ratio = t.amount / max(med[t.category], 1)
        if f == -1 and ratio >= 2.5:   # require a meaningful jump so alerts stay trustworthy
            out[t.id] = f"{ratio:.1f}× your usual {t.category} spend"
    return out


def health_score(txns, budgets, today: date):
    df = monthly_frame(txns)
    if df.empty:
        return {"score": 0, "parts": []}
    current = month_key(today)
    past = df[df["month"] < current]
    use = past if not past.empty else df
    inc = use[use["type"] == "income"].groupby("month")["amount"].sum()
    exp = use[use["type"] == "expense"].groupby("month")["amount"].sum()
    months = sorted(set(inc.index) | set(exp.index))[-6:]
    inc_t = sum(inc.get(m, 0) for m in months)
    exp_t = sum(exp.get(m, 0) for m in months)
    savings_rate = (inc_t - exp_t) / inc_t if inc_t else 0
    s1 = max(0.0, min(1.0, savings_rate / 0.30)) * 40

    cur = df[(df["month"] == current) & (df["type"] == "expense")].groupby("category")["amount"].sum()
    if budgets:
        ok = sum(1 for b in budgets if cur.get(b.category, 0) <= b.monthly_limit)
        adherence = ok / len(budgets)
    else:
        adherence = 0.5
    s2 = adherence * 30

    series = np.array([exp.get(m, 0) for m in months], dtype=float)
    cv = float(series.std() / series.mean()) if len(series) > 1 and series.mean() > 0 else 0.5
    stability = max(0.0, 1 - cv / 0.5)
    s3 = stability * 30
    score = round(s1 + s2 + s3)
    return {"score": score, "parts": [
        {"key": "savings", "label": "Savings rate", "value": round(savings_rate * 100, 1), "points": round(s1, 1), "max": 40},
        {"key": "budgets", "label": "Budgets on track", "value": round(adherence * 100, 1), "points": round(s2, 1), "max": 30},
        {"key": "stability", "label": "Spending stability", "value": round(stability * 100, 1), "points": round(s3, 1), "max": 30},
    ]}


def pace(txns, budgets, today: date):
    days = calendar.monthrange(today.year, today.month)[1]
    cur = month_key(today)
    spent = sum(t.amount for t in txns if t.type == "expense" and month_key(t.date) == cur)
    limit = sum(b.monthly_limit for b in budgets)
    projected = spent / today.day * days if today.day else spent
    return {"spent": round(spent, 2), "budget": round(limit, 2), "day": today.day, "days": days,
            "month_progress": round(today.day / days, 4),
            "budget_progress": round(spent / limit, 4) if limit else None,
            "projected": round(projected, 2)}


def rule_50_30_20(txns, today: date):
    needs = {"Rent", "Bills", "Groceries", "Health", "Education", "Transport"}
    wants = {"Food", "Shopping", "Entertainment", "Others"}
    df = monthly_frame(txns)
    cur = month_key(today)
    past = df[df["month"] < cur]
    months = sorted(past["month"].unique())[-3:]
    if not months:
        return None
    p = past[past["month"].isin(months)]
    income = p[p["type"] == "income"]["amount"].sum() / len(months)
    e = p[p["type"] == "expense"]
    n = e[e["category"].isin(needs)]["amount"].sum() / len(months)
    w = e[e["category"].isin(wants)]["amount"].sum() / len(months)
    t = e[e["category"] == "Transfers"]["amount"].sum() / len(months)
    s = income - n - w - t
    return {"income": round(income, 2),
            "actual": {"needs": round(n, 2), "wants": round(w + t, 2), "savings": round(s, 2)},
            "ideal": {"needs": round(income * .5, 2), "wants": round(income * .3, 2), "savings": round(income * .2, 2)}}
