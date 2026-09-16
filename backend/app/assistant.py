"""FinSight assistant: grounded answers about the user's own money.

LLM mode: any OpenAI-compatible chat API (Groq, Google Gemini, OpenAI, OpenRouter) via env vars.
Offline mode: a deterministic intent engine over the same data, used when no key is set or the API fails."""
import json, os, re, time
from collections import defaultdict
from datetime import date, timedelta
import httpx
from .ml import analytics as A
from .ml.dataset import EXPENSE_CATEGORIES

def _load_dotenv():
    """Read backend/.env (KEY=value lines) so Windows users don't need to set environment variables."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")


def status():
    return {"mode": "llm" if LLM_API_KEY else "offline", "model": LLM_MODEL if LLM_API_KEY else "FinSight offline engine"}


def _prev_month(d):
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)


def build_context(txns, budgets, goals, forecast, recurring, today: date):
    cur, prev = A.month_key(today), A.month_key(_prev_month(today))
    by_month = defaultdict(lambda: {"income": 0.0, "expense": 0.0, "categories": defaultdict(float)})
    merchants = defaultdict(float)
    for t in txns:
        m = by_month[A.month_key(t.date)]
        m[t.type] += t.amount
        if t.type == "expense":
            m["categories"][t.category] += t.amount
            if A.month_key(t.date) in (cur, prev):
                merchants[A._merchant(t.description).title()] += t.amount
    months = sorted(by_month)[-6:]
    cur_cats = by_month[cur]["categories"]
    return {
        "today": today.isoformat(), "current_month": cur, "day_of_month": today.day,
        "months": {m: {"income": round(by_month[m]["income"]), "expense": round(by_month[m]["expense"]),
                       "by_category": {k: round(v) for k, v in sorted(by_month[m]["categories"].items(), key=lambda x: -x[1])}}
                   for m in months},
        "budgets": [{"category": b.category, "limit": b.monthly_limit, "spent_this_month": round(cur_cats.get(b.category, 0))} for b in budgets],
        "goals": [{"name": g.name, "target": g.target, "saved": g.saved, "deadline": g.deadline.isoformat() if g.deadline else None} for g in goals],
        "next_month_forecast": {"month": forecast["month"], "total": round(forecast["total"]),
                                "by_category": {c["category"]: round(c["forecast"]) for c in forecast["categories"][:8]}},
        "recurring_bills": [{"merchant": r["merchant"], "amount": round(r["amount"]), "next_due": r["next_due"]} for r in recurring[:10]],
        "unusual_spends": [{"date": t.date.isoformat(), "description": t.description, "amount": t.amount, "reason": t.anomaly_reason}
                           for t in sorted([t for t in txns if t.is_anomaly], key=lambda t: t.date, reverse=True)[:5]],
        "top_merchants_last_2_months": {k: round(v) for k, v in sorted(merchants.items(), key=lambda x: -x[1])[:8]},
        "transaction_count": len(txns),
    }


SYSTEM = """You are FinSight's personal finance assistant for a user in India.
Answer ONLY from the JSON data provided. If the data doesn't contain the answer, say so briefly and suggest what to import or add.
Use ₹ with Indian digit grouping (₹1,25,000). Be concise: 2-6 short sentences or a few bullet points starting with "- ".
Give specific numbers and one practical next step when useful. Use **bold** sparingly for key figures. Never invent transactions.
You are not a licensed financial advisor; for investment or tax decisions, suggest confirming with a professional."""


def ask_llm(question, context, history):
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "system", "content": "User financial data (JSON):\n" + json.dumps(context, separators=(",", ":"))}]
    for m in history[-6:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": question})
    r = httpx.post(f"{LLM_BASE_URL}/chat/completions", timeout=30,
                   headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
                   json={"model": LLM_MODEL, "messages": messages, "temperature": 0.3, "max_tokens": 500})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def inr(v):
    v = round(v)
    s = str(abs(v))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return ("-₹" if v < 0 else "₹") + s


def nice_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def month_name(mk):
    import calendar
    y, m = map(int, mk.split("-"))
    return f"{calendar.month_name[m]} {y}"


def answer_offline(q, ctx):
    ql = q.lower()
    months = ctx["months"]
    cur = ctx["current_month"]
    keys = sorted(months)
    prev = keys[-2] if len(keys) >= 2 and keys[-1] == cur else (keys[-1] if keys and keys[-1] != cur else None)
    if not ctx["transaction_count"]:
        return "I don't see any transactions yet. Import a bank statement CSV on the Transactions page and I can answer questions about your spending, budgets and goals."
    target = prev if re.search(r"last month|previous month", ql) else cur
    m = months.get(target, {"income": 0, "expense": 0, "by_category": {}})
    label = "last month" if target == prev else "this month"
    cat = next((c for c in EXPENSE_CATEGORIES if re.search(rf"\b{c.lower().rstrip('s')}", ql)), None)
    if not cat:
        aliases = {"Food": r"swiggy|zomato|eat|restaurant|dining", "Transport": r"uber|ola|cab|travel|petrol|fuel",
                   "Shopping": r"amazon|flipkart|cloth", "Entertainment": r"netflix|movie|spotify", "Bills": r"electric|recharge|internet|phone"}
        cat = next((c for c, rx in aliases.items() if re.search(rx, ql)), None)

    if re.search(r"budget", ql):
        if not ctx["budgets"]:
            return "You haven't set any budgets yet. Add one on the Budgets page and I'll track it for you."
        over = [b for b in ctx["budgets"] if b["spent_this_month"] > b["limit"]]
        near = [b for b in ctx["budgets"] if b not in over and b["spent_this_month"] > 0.8 * b["limit"]]
        lines = [f"Day {ctx['day_of_month']} of the month. Across {len(ctx['budgets'])} budgets:"]
        lines += [f"- **{b['category']}** is over: {inr(b['spent_this_month'])} of {inr(b['limit'])}" for b in over]
        lines += [f"- **{b['category']}** is close: {inr(b['spent_this_month'])} of {inr(b['limit'])}" for b in near]
        if not over and not near:
            lines.append("- Everything is under 80% of its limit. Nice.")
        return "\n".join(lines)
    if re.search(r"forecast|next month|predict|expect", ql):
        f = ctx["next_month_forecast"]
        top = ", ".join(f"{k} {inr(v)}" for k, v in list(f["by_category"].items())[:3])
        return f"I expect about **{inr(f['total'])}** of spending in {month_name(f['month'])}. The biggest parts: {top}. This uses Holt-Winters smoothing on your past months, with one-off unusual spends left out."
    if re.search(r"unusual|anomal|suspicious|strange|weird", ql):
        u = ctx["unusual_spends"]
        if not u:
            return "Nothing looks unusual right now. I flag payments that are far bigger than your normal spend in that category."
        return "These stood out:\n" + "\n".join(f"- {x['description']}: **{inr(x['amount'])}** on {nice_date(x['date'])} ({x['reason']})" for x in u)
    if re.search(r"bill|subscription|recurring|emi", ql):
        r = ctx["recurring_bills"]
        if not r:
            return "I haven't spotted recurring bills yet. I need about three months of history to detect them."
        return f"You have {len(r)} recurring payments, about **{inr(sum(x['amount'] for x in r))}** a month:\n" + "\n".join(f"- {x['merchant']}: {inr(x['amount'])}, next due {nice_date(x['next_due'])}" for x in r[:6])
    if re.search(r"goal", ql):
        g = ctx["goals"]
        if not g:
            return "You don't have savings goals yet. Create one on the Goals page and I'll estimate when you'll reach it."
        return "Your goals:\n" + "\n".join(f"- **{x['name']}**: {inr(x['saved'])} of {inr(x['target'])} ({round(x['saved'] / x['target'] * 100)}%)" for x in g)
    if re.search(r"sav(e|ing)|left over|afford", ql):
        full = [k for k in keys if k != cur][-3:]
        if not full:
            return f"So far {label} you've earned {inr(m['income'])} and spent {inr(m['expense'])}."
        avg = sum(months[k]["income"] - months[k]["expense"] for k in full) / len(full)
        inc = sum(months[k]["income"] for k in full) / len(full)
        rate = avg / inc * 100 if inc else 0
        tip = "That's above the 20% target." if rate >= 20 else f"To reach 20% you'd need to save about {inr(inc * 0.2 - avg)} more a month."
        return f"Over the last {len(full)} months you saved about **{inr(avg)} a month** ({rate:.0f}% of income). {tip}"
    if re.search(r"merchant|where.*(most|money)|top|biggest|most", ql) and not cat:
        top = list(ctx["top_merchants_last_2_months"].items())[:5]
        cats = list(m["by_category"].items())[:3]
        return (f"Biggest categories {label}: " + ", ".join(f"{k} {inr(v)}" for k, v in cats) + ".\n"
                "Top merchants over the last two months:\n" + "\n".join(f"- {k}: {inr(v)}" for k, v in top))
    if re.search(r"income|earn|salary", ql):
        return f"Income {label}: **{inr(m['income'])}**." + (f" Last month it was {inr(months[prev]['income'])}." if prev and target == cur else "")
    if cat:
        amt = m["by_category"].get(cat, 0)
        other = months.get(prev if target == cur else cur, {}).get("by_category", {}).get(cat) if prev else None
        cmp = f" Last month it was {inr(other)}." if other is not None and target == cur else ""
        b = next((b for b in ctx["budgets"] if b["category"] == cat), None)
        bud = f" That's {round(amt / b['limit'] * 100)}% of your {inr(b['limit'])} budget." if b and target == cur else ""
        return f"You spent **{inr(amt)}** on {cat} {label}.{cmp}{bud}"
    if re.search(r"spen|expense|how much", ql):
        cats = list(m["by_category"].items())[:3]
        return f"You've spent **{inr(m['expense'])}** {label}" + (f", mostly on " + ", ".join(f"{k} ({inr(v)})" for k, v in cats) if cats else "") + "."
    return ("Here's a quick snapshot: " + f"{label} you've earned {inr(m['income'])} and spent {inr(m['expense'])}. "
            "You can ask things like “How much did I spend on food last month?”, “Am I over any budget?”, "
            "“What bills are coming up?” or “How much will I spend next month?”")


def reply(question, context, history):
    t0 = time.perf_counter()
    mode, err = "offline", None
    if LLM_API_KEY:
        try:
            text = ask_llm(question, context, history)
            mode = "llm"
        except Exception as e:  # network, quota or auth problems: fall back rather than fail the user
            err = type(e).__name__
            text = answer_offline(question, context)
    else:
        text = answer_offline(question, context)
    return text, mode, (time.perf_counter() - t0) * 1000, err
