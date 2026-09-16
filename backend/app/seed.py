"""Creates the demo account with six months of realistic activity."""
import random
from datetime import date, timedelta
from .db import User, Transaction, Budget
from .auth import hash_password
from .ml import dataset
from .ml.categorizer import categorizer

DEMO_EMAIL = "demo@finsight.app"
DEMO_PASSWORD = "demo1234"

DAILY = {  # category: (probability per day, min, max)
    "Food": (0.55, 90, 520), "Groceries": (0.22, 250, 1400), "Transport": (0.40, 45, 380),
    "Shopping": (0.10, 400, 2600), "Entertainment": (0.06, 150, 700), "Health": (0.05, 120, 900),
    "Others": (0.06, 60, 600), "Transfers": (0.05, 300, 2000), "Education": (0.03, 200, 1500),
}
BUDGETS = {"Food": 6500, "Groceries": 5000, "Transport": 3500, "Shopping": 5000, "Bills": 3800,
           "Entertainment": 1800, "Health": 2000, "Rent": 15000, "Education": 2500}


def _month_start(d, back):
    y, m = d.year, d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def build_transactions(user_id, today, rng):
    start = _month_start(today, 6)
    rows = []
    d = start
    while d <= today:
        if d.day == 1:
            rows.append((d, "NEFT/ACME TECHNOLOGIES SALARY", 68000, "income", "Salary"))
            rows.append((d, rng.choice(dataset.TEMPLATES["Rent"]).format(c="VELLORE", n=rng.randint(10**5, 10**6 - 1)),
                         15000, "expense", None))
        if d.day == 5:
            for t, amt in (("UPI/AIRTEL POSTPAID/{n}", 599), ("UPI/ACT FIBERNET/{c}", 999),
                           ("UPI/NETFLIX/{n}", 499), ("UPI/SPOTIFY/{n}", 119)):
                rows.append((d, t.format(c="VELLORE", n=rng.randint(10**5, 10**6 - 1)), amt, "expense", None))
        if d.day == 12:
            rows.append((d, "UPI/TNEB ELECTRICITY BOARD/{}".format(rng.randint(10**5, 10**6 - 1)),
                         rng.randint(900, 1900), "expense", None))
        if d.day == 20 and rng.random() < 0.5:
            rows.append((d, "IMPS/UPWORK FREELANCE PAYOUT", rng.randint(6000, 14000), "income", "Freelance"))
        weekend = d.weekday() >= 5
        for cat, (p, lo, hi) in DAILY.items():
            if rng.random() < p * (1.4 if weekend and cat in ("Food", "Entertainment", "Shopping") else 1):
                desc = dataset.fill(rng.choice(dataset.TEMPLATES[cat]), rng)
                rows.append((d, desc, round(rng.uniform(lo, hi) / 10) * 10 - rng.choice([0, 1]), "expense", None))
        d += timedelta(days=1)
    # a few genuinely unusual spends so anomaly detection has something real to find
    for back, desc, amt in ((4, "UPI/CROMA/CHENNAI/482910", 24999), (2, "UPI/ZOMATO/VELLORE/771203", 3860),
                            (1, "UPI/UBER/839201", 2140)):
        day = _month_start(today, back) + timedelta(days=rng.randint(8, 22))
        rows.append((day, desc, amt, "expense", None))

    exp_desc = [r[1] for r in rows if r[3] == "expense"]
    preds = iter(categorizer.predict(exp_desc))
    out = []
    for d, desc, amt, typ, cat in rows:
        conf = 1.0
        if typ == "expense":
            cat, conf, _ = next(preds)
        out.append(Transaction(user_id=user_id, date=d, description=desc, amount=float(amt), type=typ,
                               category=cat, confidence=round(conf, 4), source="seed"))
    return out


def ensure_demo(db, today=None):
    today = today or date.today()
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user:
        return user
    user = User(name="Pavan Kumar", email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
    db.add(user)
    db.flush()
    rng = random.Random(2026)
    db.add_all(build_transactions(user.id, today, rng))
    db.add_all([Budget(user_id=user.id, category=c, monthly_limit=v) for c, v in BUDGETS.items()])
    db.commit()
    from .services import refresh_anomalies
    refresh_anomalies(db, user.id)
    return user
