import io
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def user(client):
    r = client.post("/api/auth/register", json={"name": "Test User", "email": "t@example.com", "password": "secret12"})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def demo(client):
    return {"Authorization": "Bearer " + client.post("/api/auth/demo").json()["token"]}


def test_health(client):
    assert client.get("/api/health").json()["model_ready"] is True


def test_auth_errors(client, user):
    assert client.post("/api/auth/register", json={"name": "X Y", "email": "t@example.com", "password": "secret12"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "t@example.com", "password": "wrong"}).status_code == 401
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_new_user_empty_dashboard(client, user):
    d = client.get("/api/dashboard", headers=user).json()
    assert d["counts"]["transactions"] == 0 and d["health"]["score"] == 0


def test_create_autocategorises(client, user):
    r = client.post("/api/transactions", headers=user,
                    json={"date": "2026-09-02", "description": "UPI/SWIGGY/VELLORE/123456", "amount": 349})
    assert r.status_code == 201
    t = r.json()
    assert t["category"] == "Food" and t["confidence"] > 0.6 and not t["user_corrected"]


def test_correction_is_tracked(client, user):
    t = client.post("/api/transactions", headers=user,
                    json={"date": "2026-09-03", "description": "UPI/RAMESH TEA STALL/99", "amount": 40}).json()
    r = client.patch(f"/api/transactions/{t['id']}", headers=user, json={"category": "Food"})
    assert r.json()["user_corrected"] is True and r.json()["category"] == "Food"
    assert client.patch(f"/api/transactions/{t['id']}", headers=user, json={"category": "Nope"}).status_code == 422


def test_other_users_data_is_private(client, user, demo):
    t = client.get("/api/transactions", headers=demo).json()["items"][0]
    assert client.patch(f"/api/transactions/{t['id']}", headers=user, json={"amount": 1}).status_code == 404
    assert client.delete(f"/api/transactions/{t['id']}", headers=user).status_code == 404


def test_csv_import_debit_credit_and_duplicates(client, user):
    csv = client.get("/api/transactions/sample-csv").text.encode()
    r = client.post("/api/transactions/import", headers=user, files={"file": ("s.csv", io.BytesIO(csv), "text/csv")})
    body = r.json()
    assert r.status_code == 200 and body["imported"] == 8 and body["breakdown"].get("Salary") == 1
    again = client.post("/api/transactions/import", headers=user, files={"file": ("s.csv", io.BytesIO(csv), "text/csv")}).json()
    assert again["imported"] == 0 and again["duplicates"] == 8


def test_csv_signed_amount_and_bad_columns(client, user):
    csv = b"date,description,amount\n2026-08-01,UPI/UBER/1,-250\n2026-08-02,IMPS/REFUND AMAZON,500\n2026-08-03,,10\n"
    b = client.post("/api/transactions/import", headers=user, files={"file": ("a.csv", io.BytesIO(csv), "text/csv")}).json()
    assert b["imported"] == 2 and b["error_count"] == 1
    bad = client.post("/api/transactions/import", headers=user, files={"file": ("b.csv", io.BytesIO(b"foo,bar\n1,2\n"), "text/csv")})
    assert bad.status_code == 422


def test_filters_and_pagination(client, demo):
    all_ = client.get("/api/transactions?size=10", headers=demo).json()
    assert len(all_["items"]) == 10 and all_["total"] > 100
    food = client.get("/api/transactions?category=Food&size=200", headers=demo).json()
    assert all(t["category"] == "Food" for t in food["items"])
    assert client.get("/api/transactions?month=bad", headers=demo).status_code == 422


def test_demo_analytics(client, demo):
    d = client.get("/api/dashboard", headers=demo).json()
    assert d["counts"]["anomalies"] >= 1 and 0 <= d["health"]["score"] <= 100 and len(d["cashflow"]) == 6
    i = client.get("/api/insights", headers=demo).json()
    assert i["forecast"]["total"] > 0 and i["rule_50_30_20"]["income"] > 0


def test_budget_upsert_and_delete(client, user):
    r = client.put("/api/budgets", headers=user, json={"category": "Food", "monthly_limit": 5000})
    assert r.status_code == 200
    client.put("/api/budgets", headers=user, json={"category": "Food", "monthly_limit": 6000})
    b = client.get("/api/budgets", headers=user).json()["budgets"]
    assert len(b) == 1 and b[0]["limit"] == 6000
    assert client.put("/api/budgets", headers=user, json={"category": "Salary", "monthly_limit": 1}).status_code == 422
    assert client.delete(f"/api/budgets/{b[0]['id']}", headers=user).status_code == 204


def test_metrics_record_real_latency(client, demo):
    for _ in range(5):
        client.get("/api/dashboard", headers=demo)
    live = client.get("/api/metrics/live", headers=demo).json()
    assert live["requests"] >= 5 and live["dashboard_avg"] > 0 and live["p95"] >= live["p50"]
    m = client.get("/api/metrics/models", headers=demo).json()
    assert m["latest"]["accuracy"] > 90 and m["benchmarks"]["anomaly"]["precision"] == 92.0
    assert m["benchmarks"]["forecast"]["mape"] == 3.63


@pytest.fixture(scope="module")
def admin(client):
    from app import main
    main._attempts.clear()
    r = client.post("/api/auth/register", json={"name": "Boss Admin", "email": "Boss@Example.com", "password": "secret12"})
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_retrain_is_admin_only(client, demo, user, admin):
    assert client.post("/api/metrics/retrain", headers=demo).status_code == 403
    assert client.post("/api/metrics/retrain", headers=user).status_code == 403
    r = client.post("/api/metrics/retrain", headers=admin).json()
    assert r["trigger"] == "retrain" and r["accuracy"] > 90


def test_forecast_cache_invalidates_on_write(client, user):
    before = client.get("/api/dashboard", headers=user).json()["counts"]["transactions"]
    client.post("/api/transactions", headers=user, json={"date": "2026-07-10", "description": "UPI/UBER/77", "amount": 9000})
    after = client.get("/api/insights", headers=user).json()
    assert client.get("/api/dashboard", headers=user).json()["counts"]["transactions"] == before + 1
    assert any(h["month"] == "2026-07" for h in after["forecast"]["history"])


def test_goals_crud_and_projection(client, user):
    r = client.post("/api/goals", headers=user, json={"name": "Bike", "target": 60000, "saved": 10000, "emoji": "🏍️"})
    gid = r.json()["id"]
    assert client.post(f"/api/goals/{gid}/contribute", headers=user, json={"amount": 5000}).json()["saved"] == 15000
    assert client.post(f"/api/goals/{gid}/contribute", headers=user, json={"amount": -99999}).status_code == 422
    g = next(x for x in client.get("/api/goals", headers=user).json()["goals"] if x["id"] == gid)
    assert g["remaining"] == 45000 and 0 < g["progress"] < 1
    assert client.post("/api/goals", headers=user, json={"name": "X", "target": 0}).status_code == 422
    assert client.delete(f"/api/goals/{gid}", headers=user).status_code == 204


def test_goal_privacy(client, user, demo):
    gid = client.get("/api/goals", headers=demo).json()["goals"][0]["id"]
    assert client.post(f"/api/goals/{gid}/contribute", headers=user, json={"amount": 1}).status_code == 404


def test_recurring_and_notifications(client, demo):
    rec = client.get("/api/recurring", headers=demo).json()
    merchants = {i["merchant"].lower() for i in rec["items"]}
    assert "netflix" in merchants and "spotify" in merchants
    assert not any("swiggy" in m for m in merchants)          # frequent merchants aren't bills
    notes = client.get("/api/notifications", headers=demo).json()["items"]
    assert notes and all({"id", "tone", "title", "body", "link"} <= n.keys() for n in notes)
    assert len({n["id"] for n in notes}) == len(notes)


def test_assistant_offline_answers_from_data(client, demo):
    r = client.post("/api/assistant/chat", headers=demo, json={"message": "How much did I spend on food last month?"}).json()
    assert r["intent"] == "spend_category" and "Food" in r["assistant"]["content"] and "₹" in r["assistant"]["content"]
    assert r["assistant"]["ms"] is not None
    hist = client.get("/api/assistant/history", headers=demo).json()["messages"]
    assert hist[-1]["role"] == "assistant" and hist[-2]["role"] == "user"
    m = client.get("/api/metrics/models", headers=demo).json()["assistant"]
    assert m["count"] >= 1 and m["avg_ms"] >= 0


def test_assistant_empty_account(client, user):
    client.delete("/api/assistant/history", headers=user)
    fresh = client.post("/api/auth/register", json={"name": "Empty One", "email": "empty@example.com", "password": "secret12"}).json()
    h = {"Authorization": "Bearer " + fresh["token"]}
    r = client.post("/api/assistant/chat", headers=h, json={"message": "am I over budget?"}).json()
    assert "import" in r["assistant"]["content"].lower()
    for path in ["/api/goals", "/api/recurring", "/api/notifications", "/api/insights", "/api/budgets", "/api/metrics/models"]:
        assert client.get(path, headers=h).status_code == 200, path


def test_assistant_understands_varied_questions(client, demo):
    cases = {
        "How much did I spend on food last month?": ("spend_category", "Food"),
        "how much on swiggy": ("spend_merchant", "Swiggy"),
        "what did i spend in august": ("spend_total", None),
        "Am I over any budget?": ("budget_status", None),
        "how much budget left for shopping": ("budget_status", "Shopping"),
        "how much can I spend per day": ("daily_allowance", None),
        "what bills are coming up": ("recurring", None),
        "forecast for transport": ("forecast", "Transport"),
        "anything suspicious?": ("anomalies", None),
        "where does most of my money go": ("top_categories", None),
        "biggest purchase in july": ("biggest_txn", None),
        "compare this month with last month": ("compare", None),
        "what's my financial health": ("health", None),
        "do i spend more on weekends": ("weekday", None),
        "how can i save more": ("tips", None),
        "how much did I earn last month": ("income", None),
    }
    for q, (intent, cat) in cases.items():
        r = client.post("/api/assistant/chat", headers=demo, json={"message": q}).json()
        assert r["intent"] == intent, (q, r["intent"])
        if cat and intent != "spend_merchant":
            assert r["entities"]["category"] == cat, (q, r["entities"])
        assert "₹" in r["assistant"]["content"] or intent in ("health", "weekday", "anomalies"), q
        assert r["suggestions"], q
    off = client.post("/api/assistant/chat", headers=demo, json={"message": "what is the weather today"}).json()
    assert off["intent"] == "unknown"


def test_assistant_is_local_and_measured(client, demo):
    s = client.get("/api/assistant/status", headers=demo).json()
    assert s["mode"] == "local" and s["intent_accuracy"] >= 80 and s["intents"] >= 20
    m = client.get("/api/metrics/models", headers=demo).json()["assistant"]
    assert m["count"] >= 1 and m["avg_ms"] < 5000


def test_export_csv(client, demo):
    r = client.get("/api/transactions/export?type=income", headers=demo)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    lines = r.text.strip().splitlines()
    assert lines[0].lstrip("\ufeff").startswith("Date,Description") and all(",income," in l for l in lines[1:])


def test_import_excel_with_preamble_and_word_amounts(client, user):
    import datetime, openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["State Bank of India - Account Statement"]); ws.append([])
    ws.append(["Txn Date", "Description", "Debit", "Credit", "Balance"])
    ws.append([datetime.datetime(2026, 6, 5), "UPI/NETFLIX/ZZ1", "₹499.00", None, "1000"])
    ws.append([datetime.datetime(2026, 6, 6), "SALARY CREDIT ACME", None, "Fifty thousand", "51000"])
    ws.append([None, "Closing Balance", None, None, "51000"])
    buf = io.BytesIO(); wb.save(buf)
    r = client.post("/api/transactions/import", headers=user,
                    files={"file": ("sbi.xlsx", io.BytesIO(buf.getvalue()), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}).json()
    assert r["imported"] == 2 and r["file_type"] == "Excel" and r["amounts_from_words"] == 1
    assert r["breakdown"].get("Salary") == 1 and r["detected_columns"]["debit"] == "Debit"


def test_import_messy_bank_csv(client, user):
    csv = ("HDFC BANK,,\nStatement for XXXX1234,,\n,,\n"
           "Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
           '10/06/26,UPI/ZOMATO/QQ1,,10/06/26,"1,250.00",,"9,000"\n'
           "11/06/26,UPI/UBER/QQ2,,11/06/26,two hundred twelve,,8788\n"
           "12/06/26,IMPS/REFUND AMAZON QQ3,,12/06/26,,Rs. 500 Cr,9288\n"
           "13/06/26,UPI/BIGBASKET/QQ4,,13/06/26,Nil,Nil,\n").encode()
    r = client.post("/api/transactions/import", headers=user, files={"file": ("hdfc.csv", io.BytesIO(csv), "text/csv")}).json()
    assert r["imported"] == 3 and r["error_count"] == 1 and r["header_row"] == 4 and r["breakdown"].get("Refund") == 1


def test_import_rejects_other_types(client, user):
    r = client.post("/api/transactions/import", headers=user, files={"file": ("a.docx", io.BytesIO(b"PK"), "application/msword")})
    assert r.status_code == 415


def test_words_to_number_indian_scale():
    from app.statement_parser import parse_amount
    assert parse_amount("Rs. Three lakh twenty five thousand only")[0] == 325000
    assert parse_amount("(1,250.50)") == (1250.5, "expense")
    assert parse_amount("₹ 2,000 CR") == (2000.0, "income")
    assert parse_amount("one hundred rupees fifty paise")[0] == 100.5
    assert parse_amount("Nil")[0] is None


def test_ml_insights(client, demo, user):
    r = client.get("/api/ml-insights", headers=demo).json()
    seg = r["segments"]
    assert seg["k"] in (3, 4) and -1 <= seg["silhouette"] <= 1 and abs(sum(g["share"] for g in seg["groups"]) - 100) < 1
    assert len({g["name"] for g in seg["groups"]}) == seg["k"]
    assert all(t["direction"] in ("rising", "falling", "stable") for t in r["trends"]["items"])
    assert r["what_if"]["income"] > 0 and r["weekday"]["busiest"] in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    empty = client.post("/api/auth/register", json={"name": "Nobody Here", "email": "ml-empty@x.com", "password": "secret12"}).json()
    e = client.get("/api/ml-insights", headers={"Authorization": "Bearer " + empty["token"]})
    assert e.status_code == 200 and e.json()["segments"] is None


def test_login_rate_limit_and_headers(client):
    from app import main
    main._attempts.clear()
    codes = [client.post("/api/auth/login", json={"email": "nobody@x.com", "password": "wrongpass"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[-1] == 429
    main._attempts.clear()
    h = client.get("/api/health")
    assert h.headers["x-content-type-options"] == "nosniff" and h.json()["database"] == "sqlite"


def _pdf_table(rows, password=None, pages_of=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    from reportlab.lib import pdfencrypt
    buf = io.BytesIO()
    enc = pdfencrypt.StandardEncryption(password, canPrint=1) if password else None
    doc = SimpleDocTemplate(buf, pagesize=A4, encrypt=enc)
    t = Table(rows, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
    doc.build([Paragraph("HDFC BANK — Statement of Account", getSampleStyleSheet()["Title"]), Spacer(1, 12), t])
    return buf.getvalue()


def _pdf_rows(n):
    rows = [["Date", "Narration", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]]
    for i in range(n):
        rows.append([f"{(i % 27) + 1:02d}/05/26", f"UPI/SWIGGY/PDF{i:03d}", f"{100 + i}.00", "", "50,000.00"])
    rows.append(["01/05/26", "NEFT ACME SALARY PDF", "", "68,000.00", "1,18,000.00"])
    return rows


def test_import_pdf_table_multipage(client, user):
    pdf = _pdf_table(_pdf_rows(70))   # long enough to span several pages
    r = client.post("/api/transactions/import", headers=user, files={"file": ("hdfc.pdf", io.BytesIO(pdf), "application/pdf")}).json()
    assert r["file_type"] == "PDF" and r["imported"] == 71 and r["breakdown"].get("Salary") == 1, r


def test_import_pdf_password(client, user):
    pdf = _pdf_table(_pdf_rows(3)[:3] + [["03/04/26", "UPI/UBER/PWD1", "212.00", "", "1"]], password="12031999")
    f = lambda: {"file": ("locked.pdf", io.BytesIO(pdf), "application/pdf")}
    assert client.post("/api/transactions/import", headers=user, files=f()).status_code == 423
    wrong = client.post("/api/transactions/import", headers=user, files=f(), data={"password": "nope"})
    assert wrong.status_code == 423 and "incorrect" in wrong.json()["detail"]
    ok = client.post("/api/transactions/import", headers=user, files=f(), data={"password": "12031999"}).json()
    assert ok["imported"] + ok["duplicates"] == 3 and ok["error_count"] == 0


def test_import_pdf_text_lines_and_scanned(client, user):
    from reportlab.pdfgen import canvas
    buf = io.BytesIO(); c = canvas.Canvas(buf)
    c.drawString(50, 800, "State Bank of India   Account statement")
    for i, line in enumerate(["05/04/2026 UPI/NETFLIX/TXT1 499.00 10,000.00", "06/04/2026 UPI/ZOMATO/TXT2 350.50 Dr 9,649.50",
                              "07/04/2026 IMPS REFUND AMAZON TXT3 1,200.00 Cr 10,849.50"]):
        c.drawString(50, 760 - i * 20, line)
    c.save()
    r = client.post("/api/transactions/import", headers=user, files={"file": ("sbi.pdf", io.BytesIO(buf.getvalue()), "application/pdf")}).json()
    assert r["imported"] == 3 and r["breakdown"].get("Refund") == 1, r
    blank = io.BytesIO(); c = canvas.Canvas(blank); c.rect(50, 50, 200, 200, fill=1); c.save()
    s = client.post("/api/transactions/import", headers=user, files={"file": ("scan.pdf", io.BytesIO(blank.getvalue()), "application/pdf")})
    assert s.status_code == 422 and "scanned" in s.json()["detail"]


def test_user_metrics(client, demo, admin):
    from app import main
    main._attempts.clear()
    client.post("/api/auth/register", json={"name": "Metric Person", "email": "metric@x.com", "password": "secret12"})
    client.post("/api/auth/login", json={"email": "metric@x.com", "password": "secret12"})
    assert client.get("/api/metrics/users", headers=demo).status_code == 403
    m = client.get("/api/metrics/users", headers=admin).json()
    assert m["registered_users"] >= 2 and m["active_now"] >= 1 and m["total_logins"] >= m["logins_today"] >= 2
    assert m["demo_sessions"] >= 1 and len(m["series"]) == 14
    assert m["activated_users"] >= 1 and m["activated_users"] <= m["registered_users"] and "returning_users" in m
    assert "email" not in str(m)            # aggregate only, no personal data


def test_manage_reset_requires_confirmation(capsys):
    from app import manage
    assert manage.main(["manage", "reset"]) == 1
    assert "--yes" in capsys.readouterr().out


def test_admin_flag_and_public_metrics(client, demo, admin):
    assert client.get("/api/auth/me", headers=demo).json()["is_admin"] is False
    assert client.get("/api/auth/me", headers=admin).json()["is_admin"] is True     # email match is case-insensitive
    pub = client.get("/api/metrics/live", headers=demo).json()
    adm = client.get("/api/metrics/live", headers=admin).json()
    assert pub["endpoints"] is None and pub["admin"] is False and "p95" in pub
    assert isinstance(adm["endpoints"], list) and adm["admin"] is True
    assert client.get("/api/metrics/models", headers=demo).status_code == 200      # model quality stays public
    assert client.post("/api/metrics/probe", headers=demo).status_code == 403


def test_demo_corrections_never_train_the_model(client, demo):
    from app.db import SessionLocal, Transaction
    from app.services import training_corrections
    from app.seed import DEMO_EMAIL
    from app.db import User
    t = client.get("/api/transactions?size=1", headers=demo).json()["items"][0]
    client.patch(f"/api/transactions/{t['id']}", headers=demo, json={"category": "Others" if t["category"] != "Others" else "Food"})
    db = SessionLocal()
    demo_id = db.query(User.id).filter(User.email == DEMO_EMAIL).scalar()
    demo_descs = {d for (d,) in db.query(Transaction.description).filter(Transaction.user_id == demo_id, Transaction.user_corrected.is_(True))}
    assert demo_descs and not demo_descs & {d for d, _ in training_corrections(db)}
    db.close()


def test_general_rate_limit(client):
    from app import main
    old = main.API_LIMIT
    main.API_LIMIT = 5
    main._hits.clear()
    try:
        codes = [client.get("/api/meta").status_code for _ in range(7)]
        assert codes[:5] == [200] * 5 and codes[-1] == 429
        assert client.get("/api/health").status_code == 200        # health checks are never limited
    finally:
        main.API_LIMIT = old
        main._hits.clear()


def test_forecast_series_chooses_honest_method():
    import warnings
    from statsmodels.tools.sm_exceptions import ConvergenceWarning
    from app.ml.analytics import _forecast_series
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)       # no convergence warning may escape
        warnings.simplefilter("error", RuntimeWarning)
        assert _forecast_series([15000] * 6) == (15000, "constant")
        v, m = _forecast_series([1000, 1200, 1100, 1300])         # too short for Holt-Winters
        assert m == "weighted-mean" and abs(v - (1200 + 2 * 1100 + 3 * 1300) / 6) < 1e-6
        assert _forecast_series([0, 0, 500, 0, 0, 400])[1] == "weighted-mean"   # mostly empty
        v, m = _forecast_series([8000, 8400, 8100, 8900, 8600, 9200, 9000, 9500])
        assert m.startswith(("holt-winters", "weighted-mean")) and 4000 < v < 14250


def test_change_password(client, demo):
    from app import main
    main._attempts.clear()
    tok = client.post("/api/auth/register", json={"name": "Pass Changer", "email": "pw@x.com", "password": "oldpass1"}).json()["token"]
    h = {"Authorization": "Bearer " + tok}
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "wrong", "new_password": "newpass1"}).status_code == 400
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "oldpass1", "new_password": "oldpass1"}).status_code == 422
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "oldpass1", "new_password": "123"}).status_code == 422
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "oldpass1", "new_password": "newpass1"}).status_code == 204
    assert client.post("/api/auth/login", json={"email": "pw@x.com", "password": "oldpass1"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "pw@x.com", "password": "newpass1"}).status_code == 200
    assert client.post("/api/auth/change-password", headers=demo, json={"current_password": "demo1234", "new_password": "hacked99"}).status_code == 403
    main._attempts.clear()


def test_manage_set_password(monkeypatch, capsys, client):
    from app import manage, main
    main._attempts.clear()
    client.post("/api/auth/register", json={"name": "Forgot Me", "email": "forgot@x.com", "password": "lostpass"})
    answers = iter(["freshpw1", "freshpw1"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    assert manage.main(["manage", "set-password", "Forgot@X.com"]) == 0
    assert client.post("/api/auth/login", json={"email": "forgot@x.com", "password": "freshpw1"}).status_code == 200
    answers2 = iter(["abcdef1", "different"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers2))
    assert manage.main(["manage", "set-password", "forgot@x.com"]) == 1 and "didn't match" in capsys.readouterr().out
    main._attempts.clear()
