"""Tests for the FastAPI backend (runs against a temporary SQLite database).

Run with:  python -m pytest -q
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_store
from budget import sample_data
from budget.storage import BudgetStore


@pytest.fixture
def client(tmp_path):
    store = BudgetStore(tmp_path / "api.db")
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app), store
    app.dependency_overrides.clear()


@pytest.fixture
def demo(client):
    c, store = client
    store.add_many(sample_data.generate(today=date(2026, 10, 23)))
    return c, store


def test_empty_database_reports_no_data(client):
    c, _ = client
    assert c.get("/api/meta").json()["months"] == []
    assert c.get("/api/dashboard").status_code == 404


def test_frontend_is_served(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200 and "Family Budget" in r.text


def test_dashboard_and_insights(demo):
    c, _ = demo
    d = c.get("/api/dashboard", params={"month": "2026-10"}).json()
    assert d["summary"]["income"] > 0 and d["previous"]["month"] == "2026-09"
    assert len(d["trend"]) == 6
    i = c.get("/api/insights", params={"month": "2026-10"}).json()
    assert i["unnecessary"]["count"] > 0 and i["issues"]


def test_predictions_and_apply_plan(demo):
    c, store = demo
    p = c.get("/api/predictions", params={"month": "2026-09"}).json()
    assert p["available"] and p["next_month"] == "2026-10" and p["actual"] is not None
    assert 0 <= p["prob_goal"] <= 1
    r = c.post("/api/budgets/apply-plan", json={"month": "2026-10", "target": 40}).json()
    assert r["updated"] > 0 and store.budgets()


def test_add_with_knn_and_correct_category(demo):
    c, store = demo
    r = c.post("/api/transactions", json={"type": "expense", "description": "Zomato dinner order", "amount": 520,
                                          "date": "2026-10-20"}).json()
    assert r["source"] == "knn" and r["category"] == "Dining Out"
    assert c.patch(f"/api/transactions/{r['id']}", json={"category": "Groceries", "necessity": "Reasonable"}).json()["ok"]
    assert ("Zomato dinner order", "expense", "Groceries") in store.category_corrections()
    assert c.patch("/api/transactions/999999", json={"necessity": "Reasonable"}).status_code == 404


def test_rejects_bad_input(demo):
    c, _ = demo
    bad = {"type": "expense", "description": "x", "amount": -5, "date": "2026-10-20"}
    assert c.post("/api/transactions", json=bad).status_code == 422
    assert c.put("/api/budgets", json={"budgets": {"Not a category": 100}}).status_code == 400


def test_csv_import_preview_then_import(client):
    c, store = client
    csv = b"date,description,amount\n01/10/2026,UPI/SWIGGY/1234,-450\n01/10/2026,Salary credit,85000\n"
    p = c.post("/api/import/preview", files={"file": ("s.csv", csv, "text/csv")}).json()
    assert [r["type"] for r in p["rows"]] == ["expense", "income"]
    rows = [{k: v for k, v in r.items() if k not in ("confidence", "needs_review")} for r in p["rows"]]
    assert c.post("/api/import", json=rows).json()["added"] == 2
    assert len(store.transactions()) == 2


def test_models_and_patterns(demo):
    c, _ = demo
    m = c.get("/api/models").json()
    assert {"knn", "lwr", "id3", "kmeans", "em"} <= set(m)
    p = c.get("/api/patterns", params={"k": 5}).json()
    assert p["available"] and len(p["summary"]) <= 5
