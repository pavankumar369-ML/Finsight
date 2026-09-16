import io, time
from datetime import date
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from ..db import get_db, Transaction, User
from ..auth import current_user
from ..schemas import TxnIn, TxnPatch, SuggestIn
from ..ml.categorizer import categorizer
from ..ml.dataset import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from ..services import refresh_anomalies

router = APIRouter(prefix="/api", tags=["transactions"])


def ser(t: Transaction):
    return {"id": t.id, "date": t.date.isoformat(), "description": t.description, "amount": t.amount,
            "type": t.type, "category": t.category, "confidence": t.confidence, "source": t.source,
            "user_corrected": t.user_corrected, "is_anomaly": t.is_anomaly, "anomaly_reason": t.anomaly_reason}


def _valid_category(typ, cat):
    allowed = EXPENSE_CATEGORIES if typ == "expense" else INCOME_CATEGORIES
    if cat not in allowed:
        raise HTTPException(422, f"Category must be one of: {', '.join(allowed)}.")


@router.get("/meta")
def meta():
    return {"expense_categories": EXPENSE_CATEGORIES, "income_categories": INCOME_CATEGORIES}


@router.post("/categorize/suggest")
def suggest(body: SuggestIn, user: User = Depends(current_user)):
    t0 = time.perf_counter()
    cat, conf, top = categorizer.predict([body.description])[0]
    return {"category": cat, "confidence": conf, "top": [{"category": c, "p": p} for c, p in top],
            "inference_ms": round((time.perf_counter() - t0) * 1000, 3)}


def _filtered(db, user, q="", category="", type="", month="", anomaly=False):
    qry = db.query(Transaction).filter(Transaction.user_id == user.id)
    if q:
        qry = qry.filter(or_(Transaction.description.ilike(f"%{q}%"), Transaction.category.ilike(f"%{q}%")))
    if category:
        qry = qry.filter(Transaction.category == category)
    if type in ("expense", "income"):
        qry = qry.filter(Transaction.type == type)
    if month:
        try:
            y, m = map(int, month.split("-"))
            start = date(y, m, 1)
            end = date(y + (m == 12), (m % 12) + 1, 1)
        except ValueError:
            raise HTTPException(422, "Month must look like 2026-09.")
        qry = qry.filter(Transaction.date >= start, Transaction.date < end)
    if anomaly:
        qry = qry.filter(Transaction.is_anomaly.is_(True))
    return qry


@router.get("/transactions/export")
def export_csv(q: str = "", category: str = "", type: str = "", month: str = "", anomaly: bool = False,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    import csv
    rows = _filtered(db, user, q, category, type, month, anomaly).order_by(Transaction.date.desc()).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Description", "Type", "Category", "Amount", "Model confidence", "Corrected by user", "Unusual"])
    for t in rows:
        w.writerow([t.date.isoformat(), t.description, t.type, t.category, f"{t.amount:.2f}", f"{t.confidence:.2f}",
                    "yes" if t.user_corrected else "no", t.anomaly_reason or ""])
    return PlainTextResponse("\ufeff" + buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=finsight-transactions-{date.today()}.csv"})


@router.get("/transactions")
def list_txns(q: str = "", category: str = "", type: str = "", month: str = "", anomaly: bool = False,
              page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200),
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    qry = db.query(Transaction).filter(Transaction.user_id == user.id)
    if q:
        qry = qry.filter(or_(Transaction.description.ilike(f"%{q}%"), Transaction.category.ilike(f"%{q}%")))
    if category:
        qry = qry.filter(Transaction.category == category)
    if type in ("expense", "income"):
        qry = qry.filter(Transaction.type == type)
    if month:
        try:
            y, m = map(int, month.split("-"))
            start = date(y, m, 1)
            end = date(y + (m == 12), (m % 12) + 1, 1)
        except ValueError:
            raise HTTPException(422, "Month must look like 2026-09.")
        qry = qry.filter(Transaction.date >= start, Transaction.date < end)
    if anomaly:
        qry = qry.filter(Transaction.is_anomaly.is_(True))
    total = qry.count()
    sums = dict(qry.with_entities(Transaction.type, func.sum(Transaction.amount)).group_by(Transaction.type).all())
    items = qry.order_by(Transaction.date.desc(), Transaction.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"items": [ser(t) for t in items], "total": total, "page": page, "size": size,
            "income": round(sums.get("income", 0) or 0, 2), "expense": round(sums.get("expense", 0) or 0, 2)}


@router.post("/transactions", status_code=201)
def create_txn(body: TxnIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conf, corrected = 1.0, False
    if body.category:
        _valid_category(body.type, body.category)
        cat = body.category
        if body.type == "expense":
            pred, _, _ = categorizer.predict([body.description])[0]
            corrected = pred != cat   # user overrode the model: keep it as training feedback
    elif body.type == "expense":
        cat, conf, _ = categorizer.predict([body.description])[0]
    else:
        cat = "Other income"
    t = Transaction(user_id=user.id, date=body.date, description=body.description.strip(), amount=body.amount,
                    type=body.type, category=cat, confidence=round(conf, 4), user_corrected=corrected)
    db.add(t)
    db.commit()
    refresh_anomalies(db, user.id)
    db.refresh(t)
    return ser(t)


def _own(db, user, txn_id):
    t = db.get(Transaction, txn_id)
    if not t or t.user_id != user.id:
        raise HTTPException(404, "Transaction not found.")
    return t


@router.patch("/transactions/{txn_id}")
def update_txn(txn_id: int, body: TxnPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own(db, user, txn_id)
    data = body.model_dump(exclude_unset=True)
    new_type = data.get("type", t.type)
    if "category" in data:
        _valid_category(new_type, data["category"])
        if data["category"] != t.category:
            t.user_corrected = True
            t.confidence = 1.0
    elif "type" in data and data["type"] != t.type:
        data["category"] = "Other income" if new_type == "income" else categorizer.predict([t.description])[0][0]
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    refresh_anomalies(db, user.id)
    db.refresh(t)
    return ser(t)


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_txn(txn_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, user, txn_id))
    db.commit()
    refresh_anomalies(db, user.id)


SAMPLE_CSV = """Date,Narration,Debit,Credit
01/09/2026,NEFT/ACME TECHNOLOGIES SALARY,,68000
02/09/2026,UPI/SWIGGY/VELLORE/882731,349,
03/09/2026,UPI/UBER/551029,212,
04/09/2026,UPI/BIGBASKET/220391,1284,
05/09/2026,UPI/NETFLIX/100293,499,
06/09/2026,POS/DECATHLON/CHENNAI,2199,
07/09/2026,UPI/APOLLO PHARMACY/VELLORE,386,
08/09/2026,UPI/BOOKMYSHOW/VELLORE/662810,540,
"""


@router.get("/transactions/sample-csv", response_class=PlainTextResponse)
def sample_csv():
    return PlainTextResponse(SAMPLE_CSV, headers={"Content-Disposition": "attachment; filename=finsight-sample.csv"})


def _pick(cols, *names):
    for n in names:
        for c in cols:
            if n in c:
                return c
    return None


@router.post("/transactions/import")
async def import_csv(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    t0 = time.perf_counter()
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "File is larger than 5 MB. Split the statement and upload it in parts.")
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str).fillna("")
    except Exception:
        raise HTTPException(422, "This file could not be read as CSV. Export the statement as .csv and try again.")
    cols = {c: c.strip().lower() for c in df.columns}
    df = df.rename(columns=cols)
    c_date = _pick(df.columns, "date")
    c_desc = _pick(df.columns, "narration", "description", "details", "remarks", "particulars")
    c_debit = _pick(df.columns, "debit", "withdrawal")
    c_credit = _pick(df.columns, "credit", "deposit")
    c_amount = _pick(df.columns, "amount")
    c_type = _pick(df.columns, "type")
    if not c_date or not c_desc or not (c_amount or c_debit or c_credit):
        raise HTTPException(422, "Couldn't find the columns. The CSV needs Date, Description (or Narration) "
                                 "and either Amount or Debit/Credit columns.")

    def num(v):
        v = str(v).replace(",", "").replace("₹", "").strip()
        try:
            return float(v) if v else 0.0
        except ValueError:
            return 0.0

    existing = {(t.date, t.description, round(t.amount, 2), t.type) for t in
                db.query(Transaction).filter(Transaction.user_id == user.id).all()}
    signed = bool(c_amount) and not c_type and any(num(v) < 0 for v in df[c_amount])
    parsed, errors, dupes = [], [], 0
    for i, row in df.iterrows():
        d = pd.to_datetime(row[c_date], dayfirst=True, errors="coerce")
        desc = str(row[c_desc]).strip()
        if pd.isna(d) or not desc:
            errors.append(f"Row {i + 2}: missing or unreadable date/description")
            continue
        if c_amount:
            amt = num(row[c_amount])
            if c_type:
                tv = str(row[c_type]).lower()
                typ = "income" if ("cr" in tv or "income" in tv) else "expense"
                amt = abs(amt)
            elif signed:
                typ, amt = ("income", amt) if amt > 0 else ("expense", -amt)
            else:
                typ = "expense"
        else:
            dr, cr = num(row[c_debit]) if c_debit else 0, num(row[c_credit]) if c_credit else 0
            typ, amt = ("income", cr) if cr > 0 else ("expense", dr)
        if amt <= 0:
            errors.append(f"Row {i + 2}: amount is zero or missing")
            continue
        key = (d.date(), desc, round(amt, 2), typ)
        if key in existing:
            dupes += 1
            continue
        existing.add(key)
        parsed.append(key)

    exp_idx = [k for k, p in enumerate(parsed) if p[3] == "expense"]
    preds = categorizer.predict([parsed[k][1] for k in exp_idx]) if exp_idx else []
    pmap = dict(zip(exp_idx, preds))
    breakdown, low = {}, 0
    new = []
    for k, (d, desc, amt, typ) in enumerate(parsed):
        if typ == "expense":
            cat, conf, _ = pmap[k]
            low += conf < 0.6
        else:
            cat, conf = ("Salary" if "salary" in desc.lower() else "Other income"), 1.0
        breakdown[cat] = breakdown.get(cat, 0) + 1
        new.append(Transaction(user_id=user.id, date=d, description=desc, amount=amt, type=typ,
                               category=cat, confidence=round(conf, 4), source="csv"))
    db.add_all(new)
    db.commit()
    flagged = refresh_anomalies(db, user.id)
    return {"imported": len(new), "duplicates": dupes, "errors": errors[:20], "error_count": len(errors),
            "low_confidence": int(low), "breakdown": breakdown, "anomalies_total": flagged,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)}
