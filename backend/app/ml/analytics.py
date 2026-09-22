"""Forecasting, anomaly detection, financial health score and budget pace."""
import calendar, math, warnings
from collections import defaultdict
from datetime import date
import numpy as np
# pandas is deliberately NOT used here: these aggregations are simple sums, and importing pandas
# costs seconds on a throttled free-tier CPU just to render the dashboard.



def month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _sums(txns, key):
    """Sum amounts grouped by key(t) -> {group: total}. Plain-Python replacement for a pandas groupby."""
    out = defaultdict(float)
    for t in txns:
        out[key(t)] += t.amount
    return out


MIN_MONTHS_FOR_HW = 6      # damped Holt-Winters estimates ~4 parameters; fewer points than this is an unreliable fit


def _weighted_recent(vals):
    """Recency-weighted mean of the last 3 months (weights 1, 2, 3)."""
    recent = vals[-3:]
    return float(np.average(recent, weights=np.arange(1, len(recent) + 1)))


def _forecast_series(values):
    """values: monthly totals oldest->newest (complete months). Returns (forecast, method).

    Holt-Winters only when the series can support it: at least 6 months and not mostly empty.
    If the optimiser fails to converge, its parameters aren't trustworthy, so we fall back
    to a recency-weighted mean instead of using a shaky fit."""
    vals = [float(v) for v in values]
    if len(vals) == 0:
        return 0.0, "no-data"
    zeros = sum(1 for v in vals if v == 0)
    if max(vals) - min(vals) < 1e-9:
        return vals[-1], "constant"          # e.g. fixed rent: nothing to model
    if len(vals) < MIN_MONTHS_FOR_HW or zeros >= len(vals) / 2:
        return _weighted_recent(vals), "weighted-mean"
    try:
        from statsmodels.tools.sm_exceptions import ConvergenceWarning
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        # np.errstate: statsmodels also computes AIC/BIC, which hit log(0) on near-perfect fits; we don't use them
        with warnings.catch_warnings(record=True) as caught, np.errstate(divide="ignore", invalid="ignore"):
            warnings.simplefilter("always", ConvergenceWarning)
            model = ExponentialSmoothing(np.array(vals), trend="add", damped_trend=True,
                                         initialization_method="estimated").fit()
        if any(issubclass(w.category, ConvergenceWarning) for w in caught):
            return _weighted_recent(vals), "weighted-mean (fit did not converge)"
        f = float(model.forecast(1)[0])
        if not np.isfinite(f):
            return _weighted_recent(vals), "weighted-mean"
        # guard against wild extrapolation on short histories
        lo, hi = min(vals) * 0.5, max(vals) * 1.5
        return max(lo, min(hi, f)), "holt-winters"
    except Exception:
        return _weighted_recent(vals), "weighted-mean"


def forecast(txns, today: date):
    """Forecast next month's spend per category using complete past months."""
    # anomalies are one-off events; leaving them in would drag every future forecast upward
    exp = [t for t in txns if t.type == "expense" and not t.is_anomaly]
    current = month_key(today)
    if not exp:
        return {"month": None, "total": 0, "categories": [], "history": [], "backtest_mape": None}
    past = [t for t in exp if month_key(t.date) < current]
    months = sorted({month_key(t.date) for t in past})
    by = _sums(past, lambda t: (t.category, month_key(t.date)))
    categories = sorted({t.category for t in past})            # pandas pivot orders columns alphabetically
    series = {c: [by.get((c, m), 0.0) for m in months] for c in categories}
    cats = []
    for cat in categories:
        f, method = _forecast_series(series[cat])
        cats.append({"category": cat, "forecast": round(f, 2), "method": method,
                     "last": round(float(series[cat][-1]), 2) if months else 0})
    cats.sort(key=lambda c: -c["forecast"])
    totals = [sum(series[c][i] for c in categories) for i in range(len(months))]
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
    from sklearn.ensemble import IsolationForest
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
    if not txns:
        return {"score": 0, "parts": []}
    current = month_key(today)
    past = [t for t in txns if month_key(t.date) < current]
    use = past if past else txns
    inc = _sums([t for t in use if t.type == "income"], lambda t: month_key(t.date))
    exp = _sums([t for t in use if t.type == "expense"], lambda t: month_key(t.date))
    months = sorted(set(inc) | set(exp))[-6:]
    inc_t = sum(inc.get(m, 0) for m in months)
    exp_t = sum(exp.get(m, 0) for m in months)
    savings_rate = (inc_t - exp_t) / inc_t if inc_t else 0
    s1 = max(0.0, min(1.0, savings_rate / 0.30)) * 40

    cur = _sums([t for t in txns if t.type == "expense" and month_key(t.date) == current], lambda t: t.category)
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
    cur = month_key(today)
    past = [t for t in txns if month_key(t.date) < cur]
    months = sorted({month_key(t.date) for t in past})[-3:]
    if not months:
        return None
    ms = set(months)
    p = [t for t in past if month_key(t.date) in ms]
    income = sum(t.amount for t in p if t.type == "income") / len(months)
    e = [t for t in p if t.type == "expense"]
    n = sum(t.amount for t in e if t.category in needs) / len(months)
    w = sum(t.amount for t in e if t.category in wants) / len(months)
    tr = sum(t.amount for t in e if t.category == "Transfers") / len(months)
    s = income - n - w - tr
    return {"income": round(income, 2),
            "actual": {"needs": round(n, 2), "wants": round(w + tr, 2), "savings": round(s, 2)},
            "ideal": {"needs": round(income * .5, 2), "wants": round(income * .3, 2), "savings": round(income * .2, 2)}}


def _merchant(desc: str) -> str:
    import re
    t = desc.upper()
    t = re.sub(r"\d{3,}", " ", t)
    parts = [p.strip() for p in re.split(r"[/]", t) if p.strip()]
    skip = {"UPI", "POS", "NEFT", "IMPS", "MISC", "ATM WDL"}
    parts = [p for p in parts if p not in skip]
    return re.sub(r"\s+", " ", parts[0]).strip() if parts else t.strip()


def detect_recurring(txns, today: date):
    """Payments to the same merchant in 3+ separate months, roughly monthly, with a stable amount."""
    groups = defaultdict(list)
    for t in txns:
        if t.type == "expense":
            groups[(_merchant(t.description), t.category)].append(t)
    out = []
    for (merchant, cat), items in groups.items():
        by_month = {}
        for t in sorted(items, key=lambda t: t.date):
            by_month.setdefault(month_key(t.date), t)
        if len(by_month) < 3:
            continue
        firsts = sorted(by_month.values(), key=lambda t: t.date)
        amounts = np.array([t.amount for t in firsts])
        cv = amounts.std() / amounts.mean() if amounts.mean() else 1
        # a merchant you use every few days (Swiggy) isn't a bill; bills appear about once a month
        per_month = len(items) / len(by_month)
        if cv > 0.35 or per_month > 1.6:
            continue
        gaps = [(b.date - a.date).days for a, b in zip(firsts, firsts[1:])]
        if not gaps or not all(20 <= g <= 40 for g in gaps[-3:]):
            continue
        day = int(np.median([t.date.day for t in firsts]))
        y, m = today.year, today.month
        paid_this_month = month_key(today) in by_month
        if paid_this_month or today.day > day + 3:
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        due = date(y, m, min(day, calendar.monthrange(y, m)[1]))
        out.append({"merchant": merchant.title(), "category": cat, "amount": round(float(amounts[-3:].mean()), 2),
                    "last_amount": round(float(firsts[-1].amount), 2), "last_paid": firsts[-1].date.isoformat(),
                    "months": len(by_month), "next_due": due.isoformat(), "days_until": (due - today).days,
                    "variable": bool(cv > 0.08)})
    out.sort(key=lambda r: r["days_until"])
    return out


def avg_monthly_savings(txns, today: date, months=3):
    if not txns:
        return 0.0
    cur = month_key(today)
    past = [t for t in txns if month_key(t.date) < cur]
    ms = sorted({month_key(t.date) for t in past})[-months:]
    if not ms:
        return 0.0
    keep = set(ms)
    p = [t for t in past if month_key(t.date) in keep]
    return float((sum(t.amount for t in p if t.type == "income") - sum(t.amount for t in p if t.type == "expense")) / len(ms))
