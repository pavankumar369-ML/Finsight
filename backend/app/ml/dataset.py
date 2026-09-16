"""Labelled transaction-description dataset in Indian bank-statement style (UPI / POS / NEFT / IMPS)."""
import random

EXPENSE_CATEGORIES = ["Food", "Groceries", "Transport", "Shopping", "Bills", "Entertainment",
                      "Health", "Education", "Rent", "Transfers", "Others"]
INCOME_CATEGORIES = ["Salary", "Freelance", "Refund", "Other income"]

TEMPLATES = {
    "Food": ["UPI/SWIGGY/{c}/{n}", "UPI/ZOMATO/{c}/{n}", "POS/DOMINOS PIZZA/{c}", "UPI/{c} RESTAURANT/{n}",
             "UPI/CHAI POINT/{c}", "UPI/MCDONALDS/{c}/{n}", "UPI/STARBUCKS/{c}", "POS/KFC/{c}/{n}",
             "UPI/BURGER KING/{n}", "UPI/{c} BIRYANI HOUSE/{n}", "UPI/CAFE COFFEE DAY/{c}"],
    "Groceries": ["UPI/BIGBASKET/{n}", "UPI/DMART/{c}", "POS/RELIANCE FRESH/{c}", "UPI/BLINKIT/{n}",
                  "UPI/ZEPTO/{n}", "POS/MORE SUPERMARKET/{c}", "UPI/{c} KIRANA STORE/{n}", "UPI/JIOMART/{n}"],
    "Transport": ["UPI/UBER/{n}", "UPI/OLA CABS/{n}", "UPI/RAPIDO/{n}", "POS/INDIAN OIL/{c}", "UPI/METRO RECHARGE/{c}",
                  "UPI/IRCTC/{n}", "POS/HP PETROL PUMP/{c}", "UPI/REDBUS/{n}", "UPI/FASTAG RECHARGE/{n}"],
    "Shopping": ["UPI/AMAZON/{n}", "UPI/FLIPKART/{n}", "POS/MYNTRA/{c}", "UPI/AJIO/{n}", "POS/{c} MALL/{n}",
                 "UPI/NYKAA/{n}", "POS/DECATHLON/{c}", "UPI/CROMA/{c}/{n}", "POS/LIFESTYLE/{c}"],
    "Bills": ["UPI/{c} ELECTRICITY BOARD/{n}", "UPI/AIRTEL POSTPAID/{n}", "UPI/JIO RECHARGE/{n}",
              "NEFT/{c} WATER BOARD/{n}", "UPI/ACT FIBERNET/{c}", "UPI/BESCOM BILL/{n}", "UPI/VI RECHARGE/{n}",
              "UPI/TATA PLAY DTH/{n}", "UPI/INDANE GAS/{n}"],
    "Entertainment": ["UPI/NETFLIX/{n}", "UPI/SPOTIFY/{n}", "UPI/BOOKMYSHOW/{c}/{n}", "UPI/PVR CINEMAS/{c}",
                      "UPI/HOTSTAR/{n}", "UPI/STEAM GAMES/{n}", "UPI/YOUTUBE PREMIUM/{n}", "POS/INOX/{c}"],
    "Health": ["UPI/APOLLO PHARMACY/{c}", "UPI/{c} HOSPITAL/{n}", "POS/MEDPLUS/{c}", "UPI/PRACTO/{n}",
               "UPI/CULT FIT/{n}", "UPI/1MG/{n}", "UPI/{c} DENTAL CLINIC/{n}", "UPI/PHARMEASY/{n}"],
    "Education": ["UPI/{c} COACHING CENTRE/{n}", "NEFT/{c} UNIVERSITY FEE/{n}", "UPI/UDEMY/{n}", "UPI/COURSERA/{n}",
                  "POS/{c} BOOK DEPOT/{n}", "UPI/UNACADEMY/{n}", "UPI/LEETCODE PREMIUM/{n}"],
    "Rent": ["NEFT/{c} RENT PAYMENT/{n}", "IMPS/HOUSE OWNER {c}/{n}", "UPI/NOBROKER RENT/{n}", "NEFT/PG HOSTEL {c}/{n}"],
    "Transfers": ["UPI/{c} TRANSFER/{n}", "IMPS/SELF TRANSFER/{n}", "UPI/GPAY TRANSFER {c}/{n}", "NEFT/TO FRIEND {c}/{n}"],
    "Others": ["UPI/{c} SERVICES/{n}", "POS/{c} STORE/{n}", "MISC/{c}/{n}", "UPI/{c} ENTERPRISES/{n}",
               "ATM WDL/{c}/{n}", "UPI/{c} TRADERS/{n}"],
}
CITIES = ["BANGALORE", "CHENNAI", "HYDERABAD", "MUMBAI", "PUNE", "VELLORE", "DELHI", "KOLKATA"]

# plausible confusions seen in real statements (used to inject realistic label noise)
CONFUSABLE = {"Food": "Groceries", "Groceries": "Food", "Shopping": "Others", "Others": "Shopping",
              "Transport": "Others", "Health": "Shopping", "Entertainment": "Shopping", "Bills": "Others",
              "Transfers": "Rent", "Education": "Others", "Rent": "Transfers"}


def fill(template: str, rng: random.Random) -> str:
    return template.format(c=rng.choice(CITIES), n=rng.randint(100000, 999999))


def generate(per_class: int = 427, noise: float = 0.06, seed: int = 42):
    rng = random.Random(seed)
    rows = []
    for cat, temps in TEMPLATES.items():
        for _ in range(per_class):
            label = cat
            if rng.random() < noise:
                label = CONFUSABLE[cat]
            rows.append((fill(rng.choice(temps), rng), label))
    rng.shuffle(rows)
    return rows
