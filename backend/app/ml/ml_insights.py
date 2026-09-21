"""Unsupervised and statistical insights on a user's own transactions."""
import math
from collections import defaultdict
from datetime import date
import numpy as np
# scipy/sklearn imported inside the functions that use them -- see the note in categorizer.py
from .analytics import month_key

DISCRETIONARY = {"Food", "Shopping", "Entertainment", "Others", "Transport", "Groceries"}
FIXED = {"Rent", "Bills", "Education", "Transfers"}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def segments(exp):
    """K-Means on (log amount, weekend, day of month) groups spends into behaviour patterns; k picked by silhouette."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler
    exp = [t for t in exp if t.category not in FIXED]
    if len(exp) < 40:
        return None
    X = np.array([[math.log1p(t.amount), 1.0 if t.date.weekday() >= 5 else 0.0, t.date.day / 31] for t in exp])
    Xs = StandardScaler().fit_transform(X)
    best = None
    for k in (3, 4):
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Xs)
        sc = silhouette_score(Xs, km.labels_, sample_size=min(len(Xs), 1500), random_state=42)
        if not best or sc > best[1]:
            best = (km, sc, k)
    km, sil, k = best
    total = sum(t.amount for t in exp)
    groups = []
    for c in range(k):
        items = [t for t, l in zip(exp, km.labels_) if l == c]
        amts = np.array([t.amount for t in items])
        cats = defaultdict(float)
        for t in items:
            cats[t.category] += t.amount
        groups.append({"cluster": c, "count": len(items), "avg": round(float(amts.mean()), 2), "median": round(float(np.median(amts)), 2),
                       "total": round(float(amts.sum()), 2), "share": round(float(amts.sum() / total * 100), 1),
                       "weekend_pct": round(sum(t.date.weekday() >= 5 for t in items) / len(items) * 100, 1),
                       "top_categories": [c for c, _ in sorted(cats.items(), key=lambda x: -x[1])[:3]]})
    groups.sort(key=lambda g: g["median"])
    overall = float(np.median([t.amount for t in exp]))
    for g in groups:
        items = [t for t, l in zip(exp, km.labels_) if l == g["cluster"]]
        g["avg_day"] = round(float(np.mean([t.date.day for t in items])), 1)
        # name clusters by what actually distinguishes them: size, then timing
        size = "Big-ticket purchases" if g["median"] >= 3 * overall else "Mid-size spends" if g["median"] >= 1.6 * overall else "Everyday spends"
        when = " on weekends" if g["weekend_pct"] >= 70 else " on weekdays" if g["weekend_pct"] <= 15 else ""
        part = ", early in the month" if g["avg_day"] < 11 else ", late in the month" if g["avg_day"] > 21 else ""
        g["name"] = size + when + part
    label_of = {g["cluster"]: i for i, g in enumerate(groups)}
    rng = np.random.default_rng(0)
    idx = rng.choice(len(exp), size=min(len(exp), 260), replace=False)
    points = [{"x": exp[i].date.day, "y": round(exp[i].amount, 2), "segment": label_of[int(km.labels_[i])],
               "label": exp[i].description[:32]} for i in sorted(idx)]
    for i, g in enumerate(groups):
        g["cluster"] = i
    return {"k": k, "silhouette": round(float(sil), 3), "groups": groups, "points": points, "n": len(exp)}


def _monthly(exp, today):
    cur = month_key(today)
    by = defaultdict(lambda: defaultdict(float))
    for t in exp:
        mk = month_key(t.date)
        if mk < cur and not t.is_anomaly:
            by[t.category][mk] += t.amount
    months = sorted({m for v in by.values() for m in v})
    return months, {c: [v.get(m, 0.0) for m in months] for c, v in by.items()}


def trends(exp, today):
    """Linear regression of monthly spend per category; flags statistically meaningful trends."""
    from scipy import stats
    months, series = _monthly(exp, today)
    if len(months) < 4:
        return {"months": len(months), "items": []}
    out = []
    x = np.arange(len(months))
    for cat, ys in series.items():
        y = np.array(ys)
        if y.mean() < 300:
            continue
        r = stats.linregress(x, y)
        pct = r.slope / y.mean() * 100
        significant = bool(np.isfinite(r.pvalue) and r.pvalue < 0.1 and abs(pct) >= 4)
        out.append({"category": cat, "slope": round(float(r.slope), 2), "pct_per_month": round(float(pct), 1),
                    "r2": round(float(r.rvalue ** 2), 3), "p_value": round(float(r.pvalue), 4),
                    "direction": ("rising" if pct > 0 else "falling") if significant else "stable",
                    "mean": round(float(y.mean()), 2), "series": [round(v, 2) for v in ys]})
    out.sort(key=lambda t: (t["direction"] == "stable", -abs(t["pct_per_month"])))
    return {"months": len(months), "month_labels": months, "items": out}


def drivers(exp, today):
    """Share of month-to-month variance in total spend explained by each category (covariance decomposition)."""
    months, series = _monthly(exp, today)
    if len(months) < 3:
        return []
    mat = np.array(list(series.values()))
    total = mat.sum(axis=0)
    var = total.var()
    if var <= 0:
        return []
    out = [{"category": c, "share": round(float(np.cov(row, total, bias=True)[0, 1] / var * 100), 1),
            "std": round(float(row.std()), 2)} for c, row in zip(series, mat)]
    return sorted(out, key=lambda d: -d["share"])


def weekday_pattern(exp):
    disc = [t for t in exp if t.category in DISCRETIONARY and not t.is_anomaly]
    if len(disc) < 20:
        return None
    first, last = min(t.date for t in disc), max(t.date for t in disc)
    weeks = max((last - first).days / 7, 1)
    sums = [0.0] * 7
    counts = [0] * 7
    for t in disc:
        sums[t.date.weekday()] += t.amount
        counts[t.date.weekday()] += 1
    per_day = [s / weeks for s in sums]
    wkday, wkend = np.mean(per_day[:5]), np.mean(per_day[5:])
    busiest = int(np.argmax(per_day))
    return {"days": [{"day": WEEKDAYS[i], "avg": round(per_day[i], 2), "count": counts[i]} for i in range(7)],
            "weekend_premium_pct": round(float((wkend - wkday) / wkday * 100), 1) if wkday else None,
            "busiest": WEEKDAYS[busiest]}


def what_if_base(txns, today):
    months, series = _monthly([t for t in txns if t.type == "expense"], today)
    use = months[-3:]
    if not use:
        return None
    idx = [months.index(m) for m in use]
    cats = {c: round(float(np.mean([v[i] for i in idx])), 2) for c, v in series.items()}
    inc = defaultdict(float)
    for t in txns:
        if t.type == "income" and month_key(t.date) in use:
            inc[month_key(t.date)] += t.amount
    income = float(np.mean([inc.get(m, 0) for m in use]))
    spend_all = defaultdict(float)
    for t in txns:
        if t.type == "expense" and month_key(t.date) in use:
            spend_all[month_key(t.date)] += t.amount
    expense = float(np.mean([spend_all.get(m, 0) for m in use]))
    return {"months": use, "income": round(income, 2), "expense": round(expense, 2), "savings": round(income - expense, 2),
            "categories": dict(sorted(cats.items(), key=lambda x: -x[1]))}


def _clean(o):
    """Replace NaN/inf (e.g. regression on a flat series) with None so the response is valid JSON."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def build(txns, today: date):
    exp = [t for t in txns if t.type == "expense"]
    return _clean({"segments": segments(exp), "trends": trends(exp, today), "drivers": drivers(exp, today),
            "weekday": weekday_pattern(exp), "what_if": what_if_base(txns, today)})
