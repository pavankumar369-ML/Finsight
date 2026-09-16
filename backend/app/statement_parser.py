"""Robust bank-statement reader for CSV, XLSX and XLS files.

Real statements are messy: preamble rows above the header, 'Withdrawal Amt.' style headers,
amounts like '₹1,250.00 Dr', '(500)', 'Nil', or even words ('two thousand five hundred'),
Excel serial dates and summary rows such as 'Opening Balance'. This module normalises all of that."""
import csv, io, re
from datetime import datetime, timedelta
import pandas as pd

MAX_ROWS = 20000

UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
SCALES = {"hundred": 100, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
          "million": 1_000_000, "crore": 10_000_000, "crores": 10_000_000}
DEBIT_WORDS = r"\b(dr|debit|debited|withdrawal|withdrawn|paid|sent|spent|expense|purchase|out)\b"
CREDIT_WORDS = r"\b(cr|credit|credited|deposit|deposited|received|refund|income|salary|in)\b"
SKIP_DESC = re.compile(r"^(opening|closing|brought|carried)\s+(balance|forward)|^total\b|^balance\b|statement summary", re.I)


def words_to_number(text: str):
    """'two thousand five hundred' -> 2500.0 ; returns None if it isn't a number phrase."""
    t = re.sub(r"[^a-z ]", " ", text.lower())
    t = re.sub(r"\b(rupees?|rs|inr|only|and)\b", " ", t)
    tokens = t.split()
    if not tokens or any(tok not in UNITS and tok not in TENS and tok not in SCALES for tok in tokens):
        return None
    total, current = 0, 0
    for tok in tokens:
        if tok in UNITS:
            current += UNITS[tok]
        elif tok in TENS:
            current += TENS[tok]
        elif tok == "hundred":
            current = (current or 1) * 100
        else:
            total += (current or 1) * SCALES[tok]
            current = 0
    return float(total + current)


def _paise_split(text):
    low = text.lower()
    if "paise" not in low:
        return words_to_number(text)
    m = re.match(r"(.*?)(?:rupees?|rs\.?)\s+(.*)paise", low)
    if not m:
        return None
    rupees, paise = words_to_number(m.group(1)), words_to_number(m.group(2))
    if rupees is None or paise is None:
        return None
    return rupees + paise / 100


def parse_amount(value):
    """Returns (amount or None, direction) where direction is 'expense', 'income' or None."""
    if value is None:
        return None, None
    s = str(value).strip()
    if not s or s.lower() in {"nil", "na", "n/a", "-", "--", "nan", "none", "null", "0.00", "0"}:
        return (0.0 if s in {"0", "0.00"} else None), None
    low = s.lower()
    direction = None
    if re.search(DEBIT_WORDS, low):
        direction = "expense"
    elif re.search(CREDIT_WORDS, low):
        direction = "income"
    negative = low.startswith("-") or low.startswith("(") and low.endswith(")") or low.endswith("-")
    cleaned = re.sub(r"(₹|rs\.?|inr|\bdr\b|\bcr\b|debit|credit|[()])", " ", low)
    cleaned = cleaned.replace(",", "").strip()
    num = re.search(r"-?\d+(\.\d+)?", cleaned)
    if num and not re.search(r"[a-z]{3,}", re.sub(r"\b(rupees?|only)\b", "", cleaned)):
        amount = abs(float(num.group()))
    else:
        amount = _paise_split(s)
        if amount is None:
            return None, direction
    if negative and direction is None:
        direction = "expense"
    return amount, direction


def parse_date(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "nat", "none"}:
        return None
    if re.fullmatch(r"\d{5}(\.0+)?", s):                       # Excel serial date
        n = int(float(s))
        if 20000 < n < 80000:
            return (datetime(1899, 12, 30) + timedelta(days=n)).date()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?", s):   # ISO, as Excel/pandas writes it
        return pd.to_datetime(s, errors="coerce").date()
    d = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return None if pd.isna(d) else d.date()


def read_table(raw: bytes, filename: str) -> pd.DataFrame:
    """Reads the first sheet/table as strings, with no header assumptions."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        engine = "xlrd" if name.endswith(".xls") else "openpyxl"
        try:
            sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, header=None, dtype=str, engine=engine)
        except Exception as e:
            raise ValueError("This Excel file couldn't be opened. Save it again as .xlsx or .csv and retry.") from e
        # pick the sheet that looks most like a statement (most non-empty rows)
        df = max(sheets.values(), key=lambda d: d.dropna(how="all").shape[0])
    else:
        text = None
        for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                if "\x00" in text:
                    continue
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("This file couldn't be read as text. Export the statement as .csv or .xlsx.")
        try:
            sep = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|").delimiter
        except csv.Error:
            sep = ","
        # csv.reader + padding keeps ragged rows (bank preambles have fewer columns than the table)
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=sep)][: MAX_ROWS + 60]
        if not rows:
            raise ValueError("The file is empty.")
        width = max(len(r) for r in rows)
        df = pd.DataFrame([r + [""] * (width - len(r)) for r in rows], dtype=str).replace("", None)
    df = df.dropna(axis=1, how="all").fillna("")   # keep blank rows so reported row numbers match the file
    return df.head(MAX_ROWS + 50).reset_index(drop=True)


COLS = {
    "date": ["transaction date", "txn date", "tran date", "posting date", "date", "value date", "value dt", "dt"],
    "description": ["narration", "description", "transaction details", "details", "particulars", "remarks",
                    "merchant", "payee", "transaction remarks", "info", "memo", "name"],
    "debit": ["withdrawal", "debit", "dr amount", "paid out", "money out", "spent", "dr"],
    "credit": ["deposit", "credit", "cr amount", "paid in", "money in", "received", "cr"],
    "amount": ["transaction amount", "amount", "amt", "inr", "rs"],
    "type": ["dr/cr", "cr/dr", "type", "indicator", "debit/credit", "txn type"],
}


def _norm(h):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z/ ]", " ", str(h).lower())).strip()


def map_columns(headers):
    heads = [_norm(h) for h in headers]
    used, mapping = set(), {}
    for key in ("type", "date", "description", "debit", "credit", "amount"):
        for syn in COLS[key]:
            hit = next((i for i, h in enumerate(heads) if i not in used and h and
                        (h == syn or re.search(rf"(^|\s|/){re.escape(syn)}($|\s|/|\.)", h))
                        and "balance" not in h and not (key == "date" and "value" in h and syn != "value date")), None)
            if hit is not None:
                mapping[key] = hit
                used.add(hit)
                break
    return mapping


def find_header(df):
    best, best_score = 0, -1
    for i in range(min(len(df), 40)):
        m = map_columns(df.iloc[i].tolist())
        score = ("date" in m) * 2 + ("description" in m) * 2 + any(k in m for k in ("amount", "debit", "credit")) * 2 + len(m) * 0.1
        if score > best_score:
            best, best_score = i, score
    return best, best_score


def parse_statement(raw: bytes, filename: str):
    df = read_table(raw, filename)
    if df.empty:
        raise ValueError("The file is empty.")
    h, score = find_header(df)
    headers = [str(x).strip() for x in df.iloc[h].tolist()]
    mapping = map_columns(headers)
    if "date" not in mapping or "description" not in mapping or not any(k in mapping for k in ("amount", "debit", "credit")):
        raise ValueError("Couldn't find the columns. The file needs a Date column, a Description (or Narration) "
                         "column, and either Amount or Debit/Credit columns.")
    body = df.iloc[h + 1:]

    has_split = "debit" in mapping or "credit" in mapping
    amount_col = None if has_split else mapping.get("amount")
    detected = {k: headers[v] for k, v in mapping.items() if k != "amount" or not has_split}
    if has_split:
        mapping.pop("amount", None)
    signed = amount_col is not None and "type" not in mapping and \
        any(str(v).strip().startswith("-") or str(v).strip().startswith("(") for v in body.iloc[:, amount_col])

    rows, errors, words_used = [], [], 0
    for offset, (_, r) in enumerate(body.iterrows()):
        line = h + offset + 2
        vals = r.tolist()
        desc = re.sub(r"\s+", " ", str(vals[mapping["description"]])).strip()
        raw_date = vals[mapping["date"]]
        if not desc and not str(raw_date).strip():
            continue
        if SKIP_DESC.search(desc):
            continue
        d = parse_date(raw_date)
        if not d or not desc:
            errors.append(f"Row {line}: missing or unreadable date/description")
            continue
        typ, amt = None, None
        if "debit" in mapping or "credit" in mapping:
            dr, dr_dir = parse_amount(vals[mapping["debit"]]) if "debit" in mapping else (None, None)
            cr, cr_dir = parse_amount(vals[mapping["credit"]]) if "credit" in mapping else (None, None)
            if cr:
                typ, amt = "income", cr
            elif dr:
                typ, amt = "expense", dr
            words_used += any(re.search(r"[a-z]{4,}", str(vals[mapping[k]]).lower()) and parse_amount(vals[mapping[k]])[0]
                              for k in ("debit", "credit") if k in mapping)
        if amt is None and amount_col is not None:
            cell = vals[amount_col]
            amt, direction = parse_amount(cell)
            words_used += bool(amt and re.search(r"[a-z]{4,}", str(cell).lower()) and not re.search(r"\d", str(cell)))
            if amt is not None:
                if "type" in mapping:
                    tv = str(vals[mapping["type"]]).lower()
                    typ = "income" if re.search(CREDIT_WORDS, tv) else "expense" if re.search(DEBIT_WORDS, tv) else (direction or "expense")
                elif direction:
                    typ = direction
                elif signed:
                    typ = "expense" if str(cell).strip().startswith(("-", "(")) else "income"
                else:
                    typ = "expense"
        if not amt or amt <= 0:
            errors.append(f"Row {line}: amount is zero, missing or unreadable")
            continue
        rows.append((d, desc[:200], round(float(amt), 2), typ))
        if len(rows) >= MAX_ROWS:
            errors.append(f"Stopped at {MAX_ROWS} rows. Split larger statements into parts.")
            break
    return {"rows": rows, "errors": errors, "detected": detected, "header_row": h + 1, "amounts_from_words": int(words_used)}
