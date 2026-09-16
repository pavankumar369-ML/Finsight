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
