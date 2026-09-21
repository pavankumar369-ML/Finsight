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


def test_retrain_uses_corrections(client, demo):
    r = client.post("/api/metrics/retrain", headers=demo).json()
    assert r["trigger"] == "retrain" and r["n_corrections"] >= 1 and r["accuracy"] > 90


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
    assert r["assistant"]["mode"] == "offline" and "Food" in r["assistant"]["content"] and "₹" in r["assistant"]["content"]
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


def test_assistant_llm_path_and_fallback(client, demo, monkeypatch):
    from app import assistant as AI
    seen = {}

    def fake_llm(question, context, history):
        seen["ctx"] = context
        return "You spent **₹7,399** on food last month."
    monkeypatch.setattr(AI, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(AI, "ask_llm", fake_llm)
    r = client.post("/api/assistant/chat", headers=demo, json={"message": "food last month?"}).json()
    assert r["assistant"]["mode"] == "llm" and "budgets" in seen["ctx"] and seen["ctx"]["transaction_count"] > 100

    def broken(*a):
        raise TimeoutError("api down")
    monkeypatch.setattr(AI, "ask_llm", broken)
    r = client.post("/api/assistant/chat", headers=demo, json={"message": "food last month?"}).json()
    assert r["assistant"]["mode"] == "offline" and r["fallback_reason"] == "TimeoutError"


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


def test_user_metrics(client, demo):
    from app import main
    main._attempts.clear()
    client.post("/api/auth/register", json={"name": "Metric Person", "email": "metric@x.com", "password": "secret12"})
    client.post("/api/auth/login", json={"email": "metric@x.com", "password": "secret12"})
    m = client.get("/api/metrics/users", headers=demo).json()
    assert m["registered_users"] >= 2 and m["active_now"] >= 1 and m["total_logins"] >= m["logins_today"] >= 2
    assert m["demo_sessions"] >= 1 and len(m["series"]) == 14
    assert "email" not in str(m)            # aggregate only, no personal data
