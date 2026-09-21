"""FinSight assistant: a local NLP engine. No external API, no data leaves the server.

1. Entity extraction finds the time period, category, merchant and goal in the question.
2. Those spans are replaced with placeholders (PERIOD, CATEGORY, MERCHANT, GOAL) so the
   intent classifier learns sentence *structure*, not specific words.
3. A TF-IDF + Logistic Regression classifier (trained on labelled example questions at startup)
   predicts one of ~20 intents.
4. A handler for that intent computes the answer from the user's own data and suggests follow-ups."""
import calendar, re, time
from collections import Counter, defaultdict
from datetime import date, timedelta
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, make_pipeline
from .ml import analytics as A

# ---------------------------------------------------------------- formatting
def inr(v):
    v = round(v)
    s = str(abs(v))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return ("-₹" if v < 0 else "₹") + s


def nice_date(d):
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d.day} {d.strftime('%b')}"


# ---------------------------------------------------------------- entities
CATEGORY_WORDS = {
    "Food": r"food|eating out|eat out|restaurants?|dining|meals?|takeaway|food delivery",
    "Groceries": r"grocer(y|ies)|vegetables|veggies|kirana|supermarket|daily essentials",
    "Transport": r"transport(ation)?|travel|cabs?|taxi|autos?|fuel|petrol|diesel|commut(e|ing)|metro|train tickets?",
    "Shopping": r"shopping|clothes|clothing|online shopping|gadgets?|electronics",
    "Bills": r"bills?|utilit(y|ies)|electricity|recharges?|internet|wifi|broadband|phone bill|mobile bill",
    "Entertainment": r"entertainment|movies?|cinema|streaming|games?|gaming|fun",
    "Health": r"health|medical|medicines?|pharmacy|doctors?|hospital|gym|fitness",
    "Education": r"education|courses?|fees|books?|college|tuition|coaching|studies",
    "Rent": r"rent|housing|hostel|pg|accommodation",
    "Transfers": r"transfers?|sent to (friends|family)|money sent",
    "Others": r"others|miscellaneous|misc",
}
CATEGORY_RX = [(c, re.compile(rf"\b({rx})\b")) for c, rx in CATEGORY_WORDS.items()]
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS.pop("may", None)
MONTH_RX = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
KNOWN_BRANDS = ["swiggy", "zomato", "uber", "ola", "rapido", "amazon", "flipkart", "myntra", "ajio", "netflix", "spotify",
                "hotstar", "bigbasket", "blinkit", "zepto", "dmart", "jiomart", "airtel", "jio", "irctc", "bookmyshow",
                "starbucks", "dominos", "kfc", "mcdonalds", "decathlon", "croma", "nykaa", "apollo", "udemy", "coursera"]


def month_bounds(y, m):
    return date(y, m, 1), date(y + (m == 12), (m % 12) + 1, 1)


def find_period(q, today):
    """Returns (start, end_exclusive, label, matched_text) or None."""
    ql = q.lower()
    rules = [
        (r"\btoday\b", lambda m: (today, today + timedelta(1), "today")),
        (r"\byesterday\b", lambda m: (today - timedelta(1), today, "yesterday")),
        (r"\bthis week\b", lambda m: (today - timedelta(today.weekday()), today + timedelta(1), "this week")),
        (r"\b(last|previous|past) week\b", lambda m: (today - timedelta(today.weekday() + 7), today - timedelta(today.weekday()), "last week")),
        (r"\b(last|past|previous) (\d{1,2}|two|three|four|five|six|twelve) months\b", None),
        (r"\b(last|previous|past) month\b", lambda m: (*month_bounds(*(lambda d: (d.year, d.month))((today.replace(day=1) - timedelta(1)))), "last month")),
        (r"\b(this|current) month\b", lambda m: (today.replace(day=1), today + timedelta(1), "this month")),
        (r"\b(this|current) year\b", lambda m: (date(today.year, 1, 1), today + timedelta(1), "this year")),
        (r"\b(all time|overall|ever|in total|so far overall|since (i )?(started|joined))\b", lambda m: (date(2000, 1, 1), today + timedelta(1), "overall")),
        (rf"\b(in |for |during )?{MONTH_RX}( (\d{{4}}))?\b", None),
    ]
    words = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "twelve": 12}
    for rx, fn in rules:
        m = re.search(rx, ql)
        if not m:
            continue
        if fn:
            s, e, label = fn(m)
            return s, e, label, m.group(0)
        if "months" in rx:
            n = int(words.get(m.group(2), m.group(2) if m.group(2).isdigit() else 3))
            n = max(1, min(n, 24))
            y, mo = today.year, today.month - (n - 1)
            while mo <= 0:
                mo += 12
                y -= 1
            return date(y, mo, 1), today + timedelta(1), f"in the last {n} months", m.group(0)
        name = m.group(2)
        if name == "may" and not re.search(r"\b(in|for|during) may\b|\bmay \d{4}\b", ql):
            continue          # "may" is usually the verb ("may go over"), not the month
        mo = MONTHS.get(name, 5 if name == "may" else MONTHS.get(name[:3]))
        yr = int(m.group(4)) if m.group(4) else (today.year if mo <= today.month else today.year - 1)
        s, e = month_bounds(yr, mo)
        return s, e, f"in {calendar.month_name[mo]} {yr}", m.group(0)
    return None


def find_category(q):
    ql = re.sub(r"financial health|health score|healthy", " ", q.lower())
    for cat, rx in CATEGORY_RX:
        m = rx.search(ql)
        if m:
            return cat, m.group(0)
    return None, None


def find_merchant(q, merchants):
    ql = q.lower()
    for mname in sorted(merchants, key=len, reverse=True):
        key = mname.lower()
        if len(key) >= 3 and re.search(rf"\b{re.escape(key)}\b", ql):
            return mname, key
        first = key.split()[0]
        if len(first) >= 5 and re.search(rf"\b{re.escape(first)}\b", ql):
            return mname, first
    for b in KNOWN_BRANDS:
        if re.search(rf"\b{b}\b", ql):
            return b.title(), b
    return None, None


def find_goal(q, goals):
    ql = q.lower()
    for g in goals:
        words = [w for w in re.findall(r"[a-z]+", g.name.lower()) if len(w) >= 3]
        if words and any(re.search(rf"\b{re.escape(w)}\b", ql) for w in words):
            return g
    return None


# ---------------------------------------------------------------- intent classifier
TRAIN = {
    "greeting": ["hi", "hello", "hey", "hey there", "good morning", "good evening", "who are you", "what can you do", "help",
                 "what can i ask you", "how does this work", "what questions can you answer", "thanks", "thank you", "ok thanks"],
    "spend_category": ["how much did i spend on CATEGORY PERIOD", "how much did i spend on CATEGORY", "CATEGORY spending PERIOD",
                       "what did i spend on CATEGORY", "total CATEGORY expenses", "how much went to CATEGORY PERIOD",
                       "my CATEGORY expenses", "how much have i spent on CATEGORY so far", "CATEGORY PERIOD",
                       "how much money on CATEGORY", "what is my CATEGORY spend PERIOD", "show CATEGORY spending",
                       "how much do i spend on CATEGORY", "amount spent on CATEGORY PERIOD", "expenses for CATEGORY"],
    "spend_merchant": ["how much did i spend at MERCHANT", "how much did i spend on MERCHANT PERIOD", "MERCHANT spending",
                       "how many times did i order from MERCHANT", "total paid to MERCHANT PERIOD", "how much on MERCHANT",
                       "how often do i use MERCHANT", "what did i pay MERCHANT", "my MERCHANT orders PERIOD",
                       "how much money went to MERCHANT", "MERCHANT PERIOD", "spent at MERCHANT"],
    "spend_total": ["how much did i spend PERIOD", "total expenses PERIOD", "what are my total expenses", "how much money did i spend",
                    "my expenses PERIOD", "total spending", "how much have i spent", "what did i spend PERIOD",
                    "how much did i spend in total", "total spent PERIOD", "overall spending", "my spending PERIOD"],
    "income": ["how much did i earn PERIOD", "what is my income", "salary PERIOD", "how much money came in", "total credits PERIOD",
               "when did i get my salary", "my earnings", "how much income did i receive", "how much did i receive PERIOD",
               "income PERIOD", "what did i earn"],
    "savings": ["how much did i save PERIOD", "what is my savings rate", "am i saving enough", "how much money is left over",
                "net savings PERIOD", "how much am i saving each month", "savings", "what are my savings",
                "how much do i save per month", "did i save money PERIOD", "what percent of income do i save"],
    "budget_status": ["am i over budget", "how are my budgets", "which budgets are exceeded", "budget status",
                      "am i within budget on CATEGORY", "how much budget is left for CATEGORY", "did i cross my CATEGORY budget",
                      "am i over any budget", "budgets PERIOD", "how much is left in my budget", "check my budgets",
                      "is my CATEGORY budget ok", "which budget is at risk"],
    "daily_allowance": ["how much can i spend per day", "daily spending limit", "how much can i spend for the rest of the month",
                        "what is my daily budget", "how much can i spend today", "safe to spend", "how much money can i still spend",
                        "daily allowance", "how much can i spend this week"],
    "forecast": ["how much will i spend next month", "predict my expenses", "forecast for CATEGORY", "expected spending next month",
                 "what will i spend PERIOD", "forecast", "next month prediction", "predict CATEGORY next month",
                 "how much should i expect to spend", "future spending"],
    "anomalies": ["any unusual transactions", "suspicious payments", "anything strange in my spending", "flagged transactions",
                  "fraud", "unusual spends", "anything weird", "abnormal transactions", "odd payments PERIOD", "anomalies"],
    "recurring": ["what CATEGORY are coming up", "upcoming CATEGORY", "when is my next CATEGORY due", "which CATEGORY are due",
                  "CATEGORY due this week", "what CATEGORY do i pay every month", "recurring CATEGORY", "what bills are coming up", "my subscriptions", "recurring payments", "when is my next bill due",
                  "upcoming payments", "emi", "which subscriptions do i pay", "monthly bills", "what do i pay every month",
                  "upcoming bills", "subscription cost", "when is MERCHANT due"],
    "goals": ["how are my goals", "when will i reach my goal", "goal progress", "how long until i reach GOAL", "my savings goals",
              "how much more do i need for GOAL", "am i on track for GOAL", "goals", "when can i afford GOAL",
              "progress on GOAL"],
    "top_categories": ["where does most of my money go", "biggest spending category", "top categories PERIOD", "spending breakdown",
                       "where did my money go PERIOD", "what do i spend the most on", "category breakdown PERIOD",
                       "which category costs the most", "split of my expenses", "where is my money going"],
    "top_merchants": ["top merchants", "where do i spend the most money", "which shops do i pay the most", "favourite places to spend",
                      "top merchants PERIOD", "which apps take most of my money", "most used merchants",
                      "who do i pay the most", "most frequent merchants"],
    "biggest_txn": ["biggest purchase PERIOD", "largest expense", "most expensive transaction", "highest payment PERIOD",
                    "what was my biggest spend", "largest transaction", "top expenses PERIOD", "big purchases"],
    "compare": ["compare this month with last month", "am i spending more than last month", "how does PERIOD compare",
                "spending change", "month over month", "is my spending going up or down", "compare months",
                "did i spend more PERIOD", "difference from last month"],
    "health": ["what is my financial health score", "how healthy are my finances", "how am i doing financially",
               "rate my finances", "health score", "am i financially healthy", "overall financial status", "give me a summary"],
    "trends": ["which spending is increasing", "spending trends", "is my CATEGORY spending going up", "what is rising",
               "trends", "which categories are growing", "any increasing expenses", "is CATEGORY trending up"],
    "weekday": ["do i spend more on weekends", "which day do i spend the most", "weekday vs weekend", "weekend spending",
                "what day is most expensive", "spending by day of week"],
    "tips": ["how can i save more", "give me tips", "how to reduce expenses", "where can i cut back", "advice",
             "how do i save money", "suggest ways to save", "help me spend less", "what should i cut", "saving tips"],
    "recent": ["show my recent transactions", "last transaction", "what did i buy recently", "how many transactions PERIOD",
               "latest payments", "recent activity", "what was my last payment", "list transactions PERIOD"],
}

MORE_TRAIN = {
    "greeting": ["hey there", "hello there", "hi assistant", "yo", "namaste", "good afternoon", "what are you", "how can you help me",
                 "what do you do", "show me what you can do", "help me", "i need help", "thanks a lot", "cool thanks"],
    "spend_category": ["how much for CATEGORY PERIOD", "CATEGORY cost PERIOD", "money spent on CATEGORY", "what was my CATEGORY bill",
                       "check CATEGORY expenses", "tell me my CATEGORY spend", "how much i spent in CATEGORY", "CATEGORY total PERIOD",
                       "spent on CATEGORY PERIOD", "how expensive was CATEGORY PERIOD"],
    "spend_merchant": ["how much have i paid MERCHANT", "MERCHANT total", "money spent on MERCHANT", "my MERCHANT bill PERIOD",
                       "how much do i spend on MERCHANT", "number of MERCHANT orders", "how many MERCHANT rides", "MERCHANT payments PERIOD",
                       "what have i spent at MERCHANT PERIOD", "check MERCHANT spending"],
    "spend_total": ["overall spending", "overall spending PERIOD", "how much money went out PERIOD", "sum of expenses", "all my expenses",
                    "total outflow PERIOD", "how much have i spent so far", "expenses PERIOD", "what is my total spend",
                    "total money spent", "how much did i pay in total PERIOD", "spending PERIOD"],
    "income": ["total credits", "total credits PERIOD", "how much money came in PERIOD", "money received PERIOD", "credited amount",
               "how much was credited", "my income PERIOD", "did i get paid PERIOD", "salary credited", "income sources",
               "how much did i make PERIOD", "inflow PERIOD"],
    "savings": ["what percent of income do i save", "savings rate PERIOD", "how much money did i keep", "net amount saved",
                "what is left after expenses", "am i saving", "saved amount PERIOD", "my monthly savings",
                "how much surplus do i have", "income minus expenses PERIOD"],
    "budget_status": ["am i overspending", "over budget", "budget check", "any budget exceeded", "am i within my budgets",
                      "status of budgets", "which CATEGORY budget is over", "budget left", "remaining budget for CATEGORY",
                      "did i exceed any limit", "how close am i to my budget", "limits status"],
    "daily_allowance": ["how much per day can i spend", "spend per day", "daily limit", "what can i spend each day",
                        "how much can i afford to spend now", "per day budget", "money left per day", "how much can i spend till month end",
                        "spending money left", "daily cap"],
    "forecast": ["what will i spend PERIOD", "next month forecast", "predict next month", "projected expenses",
                 "estimated spending next month", "forecast CATEGORY", "will i spend more next month", "expected CATEGORY next month",
                 "predicted spend", "spending prediction", "how much will CATEGORY cost next month"],
    "anomalies": ["odd payments", "odd payments PERIOD", "unexpected charges", "strange transactions", "unusual payments PERIOD",
                  "any red flags", "suspicious activity", "outliers in spending", "was anything unusual", "flag unusual spends",
                  "any fraud", "weird charges"],
    "recurring": ["emi", "emis", "my emi payments", "when is MERCHANT due", "next MERCHANT payment", "subscriptions i pay for",
                  "list my subscriptions", "repeat payments", "standing payments", "what is due soon", "bills due",
                  "monthly subscriptions cost", "autopay", "recurring charges"],
    "goals": ["my savings goals", "savings goals", "goal status", "how far am i from GOAL", "GOAL progress", "track my goals",
              "am i close to my goal", "how much left for my goal", "goal eta", "when will i hit my target", "progress towards GOAL"],
    "top_categories": ["what are my top expenses by category", "most expensive category", "where is most money spent",
                       "spend by category", "categories ranked", "highest spending categories PERIOD", "which category is biggest",
                       "breakdown PERIOD", "where does my salary go", "category wise spending"],
    "top_merchants": ["where do i spend the most money", "which merchants do i pay most", "top shops", "top payees", "most paid merchants",
                      "favourite merchants", "which stores do i use most", "biggest merchants PERIOD", "merchant ranking",
                      "top places i spend at"],
    "biggest_txn": ["highest payment", "highest payment PERIOD", "what was my biggest spend", "largest payment", "biggest expense PERIOD",
                    "most expensive purchase", "top 5 expenses", "costliest transaction", "largest purchases PERIOD", "biggest bill"],
    "compare": ["overall spending compared to last month", "vs last month", "this month versus last month", "compared with previous month",
                "am i spending less than before", "how is this month different", "month comparison", "change since last month",
                "spending more or less", "is this month worse"],
    "health": ["financial score", "how good are my finances", "money health", "am i doing well with money", "how is my financial situation",
               "financial summary", "overview of my finances", "grade my finances", "wellness score"],
    "trends": ["which categories are growing", "rising expenses", "growing spending", "is CATEGORY increasing", "any upward trend",
               "which costs are going up", "declining categories", "what is increasing over time", "trend in CATEGORY", "spending going up"],
    "weekday": ["weekend vs weekday spending", "which weekday costs most", "do i spend more on saturday", "spending on sundays",
                "busiest spending day", "day wise spending", "weekends or weekdays"],
    "tips": ["how do i save money", "ways to save", "how to spend less", "cost cutting ideas", "reduce my spending", "help me save",
             "money saving advice", "where am i wasting money", "tips to cut costs", "how can i improve my savings"],
    "recent": ["how many transactions PERIOD", "list transactions PERIOD", "recent payments", "last few transactions", "latest transactions",
               "what did i pay recently", "show transactions", "count of transactions PERIOD", "last payment", "recent spends"],
}
for _k, _v in MORE_TRAIN.items():
    TRAIN[_k] = TRAIN[_k] + [p for p in _v if p not in TRAIN[_k]]

INTENT_LABEL = {"greeting": "Help", "spend_category": "Category spend", "spend_merchant": "Merchant spend",
                "spend_total": "Total spend", "income": "Income", "savings": "Savings", "budget_status": "Budgets",
                "daily_allowance": "Daily allowance", "forecast": "Forecast", "anomalies": "Unusual spends",
                "recurring": "Bills", "goals": "Goals", "top_categories": "Top categories", "top_merchants": "Top merchants",
                "biggest_txn": "Biggest spends", "compare": "Compare months", "health": "Health score",
                "trends": "Trends", "weekday": "Weekly rhythm", "tips": "Saving tips", "recent": "Recent activity"}


def _normalise_for_training(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


class IntentModel:
    def __init__(self):
        base = [(_normalise_for_training(p), intent) for intent, phrases in TRAIN.items() for p in phrases]

        def augment(pairs):
            # light augmentation with filler words users actually type
            X, y = [], []
            for p, intent in pairs:
                for v in (p, "please " + p, "can you tell me " + p):
                    X.append(v)
                    y.append(intent)
            return X, y

        def make():
            return make_pipeline(
                FeatureUnion([("w", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                              ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True))]),
                LogisticRegression(max_iter=3000, C=8.0))
        # 5-fold cross-validation on the ORIGINAL phrases: each fold's test phrases (and all their
        # augmented variants) are unseen in training, so this measures generalisation to new wordings
        from sklearn.model_selection import StratifiedKFold
        P = np.array([p for p, _ in base])
        Y = np.array([i for _, i in base])
        accs = []
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=7).split(P, Y):
            m = make().fit(*augment(list(zip(P[tr], Y[tr]))))
            accs.append(float((m.predict(P[te]) == Y[te]).mean()))
        self.accuracy = round(float(np.mean(accs)) * 100, 1)
        self.accuracy_std = round(float(np.std(accs)) * 100, 1)
        self.n_test = len(base)
        X, y = augment(base)
        self.n_examples, self.n_intents = len(X), len(TRAIN)
        self.pipe = make().fit(X, y)

    def predict(self, text):
        p = self.pipe.predict_proba([text])[0]
        i = int(np.argmax(p))
        return self.pipe.classes_[i], float(p[i])


intent_model = IntentModel()


# ---------------------------------------------------------------- data helpers
class Ctx:
    def __init__(self, txns, budgets, goals, forecast, recurring, health, today):
        self.txns, self.budgets, self.goals = txns, budgets, goals
        self.forecast, self.recurring, self.health, self.today = forecast, recurring, health, today
        self.exp = [t for t in txns if t.type == "expense"]
        self.inc = [t for t in txns if t.type == "income"]
        self.merchants = sorted({A._merchant(t.description).title() for t in self.exp})

    def between(self, rows, s, e):
        return [t for t in rows if s <= t.date < e]

    def this_month(self):
        return self.today.replace(day=1), self.today + timedelta(1), "this month"

    def last_month(self):
        d = self.today.replace(day=1) - timedelta(1)
        return (*month_bounds(d.year, d.month), "last month")


def _sum(rows):
    return sum(t.amount for t in rows)


def _by_cat(rows):
    out = defaultdict(float)
    for t in rows:
        out[t.category] += t.amount
    return sorted(out.items(), key=lambda x: -x[1])


# ---------------------------------------------------------------- handlers: each returns (text, follow-up suggestions)
def h_greeting(c, e):
    return ("I'm FinSight's assistant. I answer from your own transactions, and nothing leaves FinSight. Try asking about "
            "spending by category, month or merchant, your budgets and daily allowance, upcoming bills, goals, forecasts, "
            "unusual spends, trends, or tips to save more.",
            ["How much did I spend this month?", "Am I over any budget?", "Where does most of my money go?", "How can I save more?"])


def h_spend_category(c, e):
    cat = e["category"]
    s, en, label = e["period"] or c.this_month()
    amt = _sum([t for t in c.between(c.exp, s, en) if t.category == cat])
    n = len([t for t in c.between(c.exp, s, en) if t.category == cat])
    lines = [f"You spent **{inr(amt)}** on {cat} {label}" + (f" across {n} payment{'s' if n != 1 else ''}." if n else ".")]
    if label == "this month":
        ls, le, _ = c.last_month()
        prev = _sum([t for t in c.between(c.exp, ls, le) if t.category == cat])
        if prev:
            lines.append(f"Last month it was {inr(prev)}.")
        b = next((b for b in c.budgets if b.category == cat), None)
        if b:
            left = b.monthly_limit - amt
            lines.append(f"That's {round(amt / b.monthly_limit * 100)}% of your {inr(b.monthly_limit)} budget, "
                         + (f"with {inr(left)} left." if left >= 0 else f"{inr(-left)} over."))
    return " ".join(lines), [f"Is my {cat.lower()} spending going up?", f"Forecast for {cat.lower()}", "Where does most of my money go?"]


def h_spend_merchant(c, e):
    name, key = e["merchant"]
    s, en, label = e["period"] or (date(2000, 1, 1), c.today + timedelta(1), "overall")
    rows = [t for t in c.between(c.exp, s, en) if key in t.description.lower()]
    if not rows:
        return f"I couldn't find payments to {name} {label}.", ["Top merchants", "Show my recent transactions"]
    amt = _sum(rows)
    avg = amt / len(rows)
    last = max(rows, key=lambda t: t.date)
    txt = (f"You paid {name} **{inr(amt)}** {label} over {len(rows)} payment{'s' if len(rows) != 1 else ''} "
           f"(about {inr(avg)} each). The latest was {inr(last.amount)} on {nice_date(last.date)}.")
    if label == "overall":
        ts, te, _ = c.this_month()
        this = _sum([t for t in c.between(c.exp, ts, te) if key in t.description.lower()])
        txt += f" This month so far: {inr(this)}."
    return txt, [f"How much did I spend on {name} last month?", "Top merchants", "How can I save more?"]


def h_spend_total(c, e):
    if e["category"]:
        return h_spend_category(c, e)
    if e["merchant"][0]:
        return h_spend_merchant(c, e)
    s, en, label = e["period"] or c.this_month()
    rows = c.between(c.exp, s, en)
    top = _by_cat(rows)[:3]
    txt = f"You spent **{inr(_sum(rows))}** {label}"
    txt += (", mostly on " + ", ".join(f"{k} ({inr(v)})" for k, v in top) + ".") if top else "."
    return txt, ["Compare this month with last month", "Biggest purchase this month", "How much can I spend per day?"]


def h_income(c, e):
    s, en, label = e["period"] or c.this_month()
    rows = c.between(c.inc, s, en)
    if not rows:
        return f"I don't see any income {label}.", ["How much did I earn last month?", "How much am I saving each month?"]
    parts = _by_cat(rows)
    return (f"Income {label}: **{inr(_sum(rows))}**" + (" (" + ", ".join(f"{k} {inr(v)}" for k, v in parts) + ")" if len(parts) > 1 else "") + ".",
            ["How much am I saving each month?", "How much did I spend this month?"])


def _complete_months(c, n=3):
    cur = c.today.replace(day=1)
    out = []
    d = cur
    for _ in range(n):
        d = (d - timedelta(1)).replace(day=1)
        out.append(month_bounds(d.year, d.month))
    return [m for m in reversed(out) if c.between(c.txns, *m)]


def h_savings(c, e):
    if e["period"]:
        s, en, label = e["period"]
        inc, exp = _sum(c.between(c.inc, s, en)), _sum(c.between(c.exp, s, en))
        rate = f" ({(inc - exp) / inc * 100:.0f}% of income)" if inc else ""
        return f"{label[0].upper() + label[1:]} you earned {inr(inc)} and spent {inr(exp)}, so you saved **{inr(inc - exp)}**{rate}.", ["How can I save more?", "How are my goals?"]
    ms = _complete_months(c)
    if not ms:
        ts, te, _ = c.this_month()
        return f"So far this month you've saved {inr(_sum(c.between(c.inc, ts, te)) - _sum(c.between(c.exp, ts, te)))}.", ["How can I save more?"]
    inc = np.mean([_sum(c.between(c.inc, *m)) for m in ms])
    exp = np.mean([_sum(c.between(c.exp, *m)) for m in ms])
    rate = (inc - exp) / inc * 100 if inc else 0
    tip = "That beats the 20% target." if rate >= 20 else f"Saving another {inr(inc * 0.2 - (inc - exp))} a month would reach 20%."
    return f"Over the last {len(ms)} complete months you saved about **{inr(inc - exp)} a month**, {rate:.0f}% of income. {tip}", \
        ["How can I save more?", "How are my goals?", "What is my financial health score?"]


def h_budget_status(c, e):
    if not c.budgets:
        return "You haven't set any budgets yet. Add them on the Budgets page and I'll track them.", ["How much did I spend this month?"]
    s, en, _ = c.this_month()
    spent = dict(_by_cat(c.between(c.exp, s, en)))
    days = calendar.monthrange(c.today.year, c.today.month)[1]
    left_days = days - c.today.day + 1
    if e["category"]:
        b = next((b for b in c.budgets if b.category == e["category"]), None)
        if not b:
            return f"There's no budget for {e['category']} yet. You've spent {inr(spent.get(e['category'], 0))} on it this month.", ["Am I over any budget?"]
        sp = spent.get(b.category, 0)
        left = b.monthly_limit - sp
        if left < 0:
            return f"{b.category} is **{inr(-left)} over** its {inr(b.monthly_limit)} budget this month.", [f"Where can I cut {b.category.lower()}?", "How can I save more?"]
        return (f"{b.category}: {inr(sp)} of {inr(b.monthly_limit)} used, **{inr(left)} left**, about {inr(left / left_days)} a day "
                f"for the remaining {left_days} days.", ["Am I over any budget?", "How much can I spend per day?"])
    over = [b for b in c.budgets if spent.get(b.category, 0) > b.monthly_limit]
    near = [b for b in c.budgets if b not in over and spent.get(b.category, 0) >= 0.8 * b.monthly_limit and b.category != "Rent"]
    lines = [f"Day {c.today.day} of {days}. Across your {len(c.budgets)} budgets:"]
    lines += [f"- **{b.category}** is over: {inr(spent.get(b.category, 0))} of {inr(b.monthly_limit)}" for b in over]
    lines += [f"- **{b.category}** is close: {inr(spent.get(b.category, 0))} of {inr(b.monthly_limit)}" for b in near]
    if not over and not near:
        lines.append("- Everything is under 80% of its limit. Nice.")
    return "\n".join(lines), ["How much can I spend per day?", "How can I save more?"]


def h_daily_allowance(c, e):
    if not c.budgets:
        return "Set budgets on the Budgets page first; then I can work out a safe daily amount.", ["How much did I spend this month?"]
    s, en, _ = c.this_month()
    days = calendar.monthrange(c.today.year, c.today.month)[1]
    left_days = days - c.today.day + 1
    fixed = {"Rent", "Bills", "Education"}
    flex = [b for b in c.budgets if b.category not in fixed]
    spent = dict(_by_cat(c.between(c.exp, s, en)))
    left = sum(b.monthly_limit - spent.get(b.category, 0) for b in flex)
    if left <= 0:
        return f"Your day-to-day budgets are already used up by {inr(-left)} this month. Try to keep to essentials until the 1st.", ["Which budgets are exceeded?", "How can I save more?"]
    return (f"You have **{inr(left)}** left across your day-to-day budgets, which is about **{inr(left / left_days)} a day** "
            f"for the remaining {left_days} days (rent and bills excluded)."), ["Am I over any budget?", "What bills are coming up?"]


def h_forecast(c, e):
    f = c.forecast
    if not f.get("month"):
        return "I need at least one complete month of data to forecast.", ["How much did I spend this month?"]
    mname = calendar.month_name[int(f["month"].split("-")[1])]
    if e["category"]:
        row = next((x for x in f["categories"] if x["category"] == e["category"]), None)
        if not row:
            return f"There isn't enough {e['category']} history to forecast it.", ["How much will I spend next month?"]
        return (f"I expect about **{inr(row['forecast'])}** on {e['category']} in {mname}, compared with {inr(row['last'])} last month."), \
            [f"Is my {e['category'].lower()} spending going up?", "How much will I spend next month?"]
    top = ", ".join(f"{x['category']} {inr(x['forecast'])}" for x in f["categories"][:3])
    return (f"I expect about **{inr(f['total'])}** of spending in {mname}. Biggest parts: {top}. "
            "This uses Holt-Winters smoothing on your past months, with one-off unusual spends left out."), \
        ["Which spending is increasing?", "How can I save more?"]


def h_anomalies(c, e):
    rows = sorted([t for t in c.txns if t.is_anomaly], key=lambda t: t.date, reverse=True)
    if e["period"]:
        rows = c.between(rows, e["period"][0], e["period"][1])
    if not rows:
        return "Nothing looks unusual. I flag payments that are far bigger than your normal spend in that category.", ["Biggest purchase this month"]
    return "These stood out:\n" + "\n".join(f"- {t.description}: **{inr(t.amount)}** on {nice_date(t.date)} ({t.anomaly_reason})" for t in rows[:5]), \
        ["Biggest purchase this month", "How can I save more?"]


def h_recurring(c, e):
    r = c.recurring
    if not r:
        return "I haven't spotted recurring bills yet. I need about three months of history to detect them.", ["Show my recent transactions"]
    soon = [x for x in r if 0 <= x["days_until"] <= 7]
    head = f"You have {len(r)} recurring payments, about **{inr(sum(x['amount'] for x in r))} a month**"
    head += f"; {len(soon)} due in the next 7 days:" if soon else ":"
    return head + "\n" + "\n".join(f"- {x['merchant']}: {inr(x['amount'])}, next due {nice_date(x['next_due'])}" for x in r[:8]), \
        ["How much can I spend per day?", "Am I over any budget?"]


def h_goals(c, e):
    if not c.goals:
        return "You don't have savings goals yet. Create one on the Goals page and I'll estimate when you'll reach it.", ["How much am I saving each month?"]
    ms = _complete_months(c)
    monthly = (np.mean([_sum(c.between(c.inc, *m)) - _sum(c.between(c.exp, *m)) for m in ms]) if ms else 0)
    active = [g for g in c.goals if g.saved < g.target] or c.goals
    share = monthly / len(active) if monthly > 0 else 0
    goals = [e["goal"]] if e["goal"] else c.goals
    lines = []
    for g in goals:
        rem = max(g.target - g.saved, 0)
        pct = round(g.saved / g.target * 100) if g.target else 0
        if rem == 0:
            lines.append(f"- {g.emoji} **{g.name}**: reached ({inr(g.saved)}).")
            continue
        eta = f"about {int(np.ceil(rem / share))} months at your current pace" if share > 0 else "no estimate yet (recent months didn't leave savings)"
        lines.append(f"- {g.emoji} **{g.name}**: {inr(g.saved)} of {inr(g.target)} ({pct}%), {inr(rem)} to go, {eta}.")
    return ("Your goal" + ("s:" if len(goals) > 1 else ":")) + "\n" + "\n".join(lines), ["How can I save more?", "How much am I saving each month?"]


def h_top_categories(c, e):
    s, en, label = e["period"] or c.this_month()
    rows = _by_cat(c.between(c.exp, s, en))
    if not rows:
        return f"No spending recorded {label}.", ["How much did I spend last month?"]
    total = sum(v for _, v in rows)
    return (f"Where your money went {label} ({inr(total)} total):\n" +
            "\n".join(f"- **{k}**: {inr(v)} ({v / total * 100:.0f}%)" for k, v in rows[:6])), \
        [f"How much did I spend on {rows[0][0].lower()} last month?", "Top merchants", "How can I save more?"]


def h_top_merchants(c, e):
    s, en, label = e["period"] or (c.last_month()[0], c.today + timedelta(1), "over the last two months")
    agg, cnt = defaultdict(float), Counter()
    for t in c.between(c.exp, s, en):
        if t.category in ("Rent", "Transfers"):
            continue
        m = A._merchant(t.description).title()
        agg[m] += t.amount
        cnt[m] += 1
    if not agg:
        return f"No merchant payments {label}.", ["Show my recent transactions"]
    top = sorted(agg.items(), key=lambda x: -x[1])[:6]
    return (f"Top merchants {label}:\n" + "\n".join(f"- **{k}**: {inr(v)} over {cnt[k]} payment{'s' if cnt[k] != 1 else ''}" for k, v in top)), \
        [f"How much did I spend at {top[0][0]}?", "Where does most of my money go?"]


def h_biggest(c, e):
    s, en, label = e["period"] or c.this_month()
    rows = sorted(c.between(c.exp, s, en), key=lambda t: -t.amount)
    if e["category"]:
        rows = [t for t in rows if t.category == e["category"]]
    if not rows:
        return f"No expenses found {label}.", ["Biggest purchase last month"]
    return (f"Biggest spends {label}:\n" + "\n".join(f"- **{inr(t.amount)}** {t.description} ({t.category}, {nice_date(t.date)})" for t in rows[:5])), \
        ["Any unusual transactions?", "Where does most of my money go?"]


def h_compare(c, e):
    ts, te, _ = c.this_month()
    ls, le, _ = c.last_month()
    day = c.today.day
    this = c.between(c.exp, ts, te)
    last_same = [t for t in c.between(c.exp, ls, le) if t.date.day <= day]
    a, b = _sum(this), _sum(last_same)
    diff = a - b
    cats_this, cats_last = dict(_by_cat(this)), dict(_by_cat(last_same))
    moves = sorted(((k, cats_this.get(k, 0) - cats_last.get(k, 0)) for k in set(cats_this) | set(cats_last)), key=lambda x: -abs(x[1]))[:3]
    direction = "more" if diff > 0 else "less"
    txt = (f"By day {day}, you've spent **{inr(a)}** this month vs {inr(b)} by the same day last month: **{inr(abs(diff))} {direction}**"
           + (f" ({abs(diff) / b * 100:.0f}%)." if b else "."))
    if moves:
        txt += "\nBiggest changes:\n" + "\n".join(f"- {k}: {'+' if v > 0 else '−'}{inr(abs(v))}" for k, v in moves)
    return txt, ["Which spending is increasing?", "How much can I spend per day?"]


def h_health(c, e):
    h = c.health
    if not h or not h.get("parts"):
        return "I need a bit more history to score your financial health.", ["How much did I spend this month?"]
    word = "healthy" if h["score"] >= 70 else "needs attention" if h["score"] >= 45 else "at risk"
    parts = "\n".join(f"- {p['label']}: {p['points']}/{p['max']}" for p in h["parts"])
    weakest = min(h["parts"], key=lambda p: p["points"] / p["max"])
    return (f"Your financial health score is **{h['score']}/100** ({word}).\n{parts}\nThe biggest gain would come from **{weakest['label'].lower()}**."), \
        ["How can I save more?", "Am I over any budget?"]


def h_trends(c, e):
    from .ml.ml_insights import trends
    tr = trends(c.exp, c.today)
    if tr["months"] < 4:
        return "Trend detection needs at least 4 complete months of data.", ["Compare this month with last month"]
    items = tr["items"]
    if e["category"]:
        x = next((i for i in items if i["category"] == e["category"]), None)
        if not x:
            return f"There's too little {e['category']} spending to test for a trend.", ["Which spending is increasing?"]
        if x["direction"] == "stable":
            return f"{e['category']} has no clear trend over {tr['months']} months (p = {x['p_value']}).", ["Which spending is increasing?"]
        return f"{e['category']} is **{x['direction']} about {abs(x['pct_per_month'])}% a month** (linear regression, p = {x['p_value']}).", [f"Forecast for {e['category'].lower()}"]
    moving = [i for i in items if i["direction"] != "stable"]
    if not moving:
        return f"No category shows a statistically clear trend over the last {tr['months']} months. Your spending is steady.", ["Where does most of my money go?"]
    return ("Clear trends (linear regression, p < 0.1):\n" + "\n".join(f"- **{i['category']}** {i['direction']} {abs(i['pct_per_month'])}% a month" for i in moving)), \
        ["How can I save more?", "How much will I spend next month?"]


def h_weekday(c, e):
    from .ml.ml_insights import weekday_pattern
    w = weekday_pattern(c.exp)
    if not w:
        return "I need more everyday transactions to see your weekly pattern.", ["Where does most of my money go?"]
    prem = w["weekend_premium_pct"]
    rel = f"about {abs(prem):.0f}% {'more' if prem > 0 else 'less'} on weekend days than weekdays" if prem is not None else "similar amounts every day"
    return f"You spend {rel}. **{w['busiest']}** is your most expensive day on average.", ["How can I save more?", "Where does most of my money go?"]


def h_tips(c, e):
    ms = _complete_months(c)
    tips = []
    if ms:
        disc = defaultdict(float)
        for m in ms:
            for k, v in _by_cat(c.between(c.exp, *m)):
                if k in {"Food", "Shopping", "Entertainment", "Others", "Transport"}:
                    disc[k] += v / len(ms)
        for k, v in sorted(disc.items(), key=lambda x: -x[1])[:2]:
            tips.append(f"- **{k}** averages {inr(v)} a month. Cutting it by 20% saves {inr(v * 0.2)} a month ({inr(v * 2.4)} a year).")
        inc = np.mean([_sum(c.between(c.inc, *m)) for m in ms])
        exp = np.mean([_sum(c.between(c.exp, *m)) for m in ms])
        if inc and (inc - exp) / inc < 0.2:
            tips.append(f"- You're saving {(inc - exp) / inc * 100:.0f}% of income. Moving {inr(inc * 0.2 - (inc - exp))} a month to savings reaches the 20% rule.")
    subs = [r for r in c.recurring if r["category"] == "Entertainment"]
    if subs:
        tips.append(f"- Subscriptions ({', '.join(r['merchant'] for r in subs)}) cost {inr(sum(r['amount'] for r in subs))} a month. Cancel any you rarely use.")
    anomalies = [t for t in c.txns if t.is_anomaly]
    if anomalies:
        tips.append(f"- {len(anomalies)} unusually large spends were flagged. Check them on the Transactions page.")
    if not tips:
        return "Import a couple of months of statements and I can give specific tips.", ["How much did I spend this month?"]
    return "Here's where you can save:\n" + "\n".join(tips[:4]), ["Which spending is increasing?", "How are my goals?"]


def h_recent(c, e):
    if e["period"]:
        rows = c.between(c.txns, e["period"][0], e["period"][1])
        return f"You have {len(rows)} transactions {e['period'][2]}: {len([t for t in rows if t.type == 'expense'])} expenses and {len([t for t in rows if t.type == 'income'])} income.", ["Where does most of my money go?"]
    rows = sorted(c.txns, key=lambda t: (t.date, t.id), reverse=True)[:5]
    if not rows:
        return "No transactions yet.", []
    return "Your latest transactions:\n" + "\n".join(f"- {nice_date(t.date)}: {t.description}, **{'+' if t.type == 'income' else '−'}{inr(t.amount)}** ({t.category})" for t in rows), \
        ["Biggest purchase this month", "How much did I spend this month?"]


HANDLERS = {"greeting": h_greeting, "spend_category": h_spend_category, "spend_merchant": h_spend_merchant, "spend_total": h_spend_total,
            "income": h_income, "savings": h_savings, "budget_status": h_budget_status, "daily_allowance": h_daily_allowance,
            "forecast": h_forecast, "anomalies": h_anomalies, "recurring": h_recurring, "goals": h_goals,
            "top_categories": h_top_categories, "top_merchants": h_top_merchants, "biggest_txn": h_biggest, "compare": h_compare,
            "health": h_health, "trends": h_trends, "weekday": h_weekday, "tips": h_tips, "recent": h_recent}


# Out-of-scope guard: a classifier always picks *some* intent, so questions with no finance vocabulary
# and no detected category/merchant/goal are treated as unknown instead of being force-fitted.
DOMAIN_RX = re.compile(r"\b(spen[dt]|spending|money|budgets?|sav(e|ed|ing|ings)|income|earn\w*|salary|bills?|pa(y|id|yments?)|"
                       r"expens\w*|costs?|transactions?|goals?|forecast\w*|predict\w*|merchants?|shops?|stores?|purchases?|"
                       r"bought|buy|orders?|subscriptions?|emis?|recurring|due|unusual|suspicious|fraud|anomal\w*|odd|strange|weird|"
                       r"categor\w*|trends?|rising|increas\w*|growing|weekends?|weekdays?|days?|tips?|advice|cut|reduce|health\w*|"
                       r"financ\w*|score|compare|comparison|versus|vs|recent|latest|last|biggest|largest|highest|top|most|afford|"
                       r"credit\w*|debit\w*|rupees?|rs|inr|₹|outflow|inflow|surplus|limit|allowance|overspend\w*|wasting|summary|overview|red flags?|outliers?|autopay|charges?|receiv\w*|make|made|limits?|cap|target|breakdown|months?|weeks?)\b")
GREETING_RX = re.compile(r"^\s*(hi|hello|hey|yo|namaste|good (morning|afternoon|evening)|thanks?|thank you|ok|cool|help|who are you|what (can|do) you|how (can|does)|what are you|i need help|show me what)\b")


def answer(question, ctx: Ctx):
    t0 = time.perf_counter()
    q = question.strip()
    ents = {"period": None, "category": None, "merchant": (None, None), "goal": None}
    norm = " " + q.lower() + " "
    p = find_period(q, ctx.today)
    if p:
        ents["period"] = p[:3]
        norm = norm.replace(p[3], " PERIOD ")
    merchant = find_merchant(q, ctx.merchants)
    if merchant[0]:
        ents["merchant"] = merchant
        norm = re.sub(rf"\b{re.escape(merchant[1])}\b", " MERCHANT ", norm)
    cat, span = find_category(norm.replace("PERIOD", "").replace("MERCHANT", ""))
    if cat:
        ents["category"] = cat
        norm = re.sub(rf"\b{re.escape(span)}\b", " CATEGORY ", norm, count=1)
    g = find_goal(q, ctx.goals)
    if g:
        ents["goal"] = g
        for w in re.findall(r"[a-z]+", g.name.lower()):
            if len(w) >= 3:
                norm = re.sub(rf"\b{re.escape(w)}\b", " GOAL ", norm)
    norm = re.sub(r"(GOAL\s*)+", "GOAL ", norm)
    norm = _normalise_for_training(norm)
    intent, conf = intent_model.predict(norm)

    # entity-aware corrections: intents that need an entity fall back sensibly without it
    if intent == "spend_category" and not cat:
        intent = "spend_merchant" if merchant[0] else "spend_total"
    if intent == "spend_merchant" and not merchant[0]:
        intent = "spend_category" if cat else "spend_total"
    if intent in ("spend_total", "spend_category") and merchant[0] and not cat:
        intent = "spend_merchant"

    if not ctx.txns and intent != "greeting":
        text, sugg = ("I don't see any transactions yet. Import a bank statement (CSV, Excel or PDF) on the Transactions page "
                      "and I can answer questions about your spending, budgets and goals.", ["What can you do?"])
        intent = "no_data"
    elif conf < 0.2 or (not GREETING_RX.search(q.lower()) and not DOMAIN_RX.search(q.lower())
                        and not (cat or merchant[0] or g)):
        text, sugg = ("I'm not sure I understood that. I can answer questions about spending (by category, merchant or month), "
                      "income, savings, budgets, bills, goals, forecasts, unusual spends, trends and saving tips.",
                      ["How much did I spend this month?", "Am I over any budget?", "What bills are coming up?", "How can I save more?"])
        intent = "unknown"
    else:
        text, sugg = HANDLERS[intent](ctx, ents)
    return {"text": text, "suggestions": sugg[:4], "intent": intent, "intent_label": INTENT_LABEL.get(intent, "Help"),
            "confidence": round(conf, 3), "ms": (time.perf_counter() - t0) * 1000,
            "entities": {"period": ents["period"][2] if ents["period"] else None, "category": ents["category"],
                         "merchant": ents["merchant"][0], "goal": ents["goal"].name if ents["goal"] else None}}


def status():
    return {"mode": "local", "model": "FinSight NLP engine", "intents": intent_model.n_intents,
            "intent_accuracy": intent_model.accuracy, "intent_accuracy_std": intent_model.accuracy_std,
            "training_examples": intent_model.n_examples, "base_phrases": intent_model.n_test, "evaluation": "5-fold cross-validation"}
