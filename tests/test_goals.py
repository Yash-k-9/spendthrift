"""Tests for spending plans, over-target alerts and the rewards game.

Run with:  python -m pytest -q
"""

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as main
from budget import goals, sample_data
from budget.storage import BudgetStore

TODAY = date(2026, 10, 20)


def frame(rows):
    df = pd.DataFrame([{"id": i + 1, "member": "Family", "necessity": None, "source": "manual", **r}
                       for i, r in enumerate(rows)])
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.strftime("%Y-%m")
    return df


PLAN = {"id": 1, "name": "October", "start_date": "2026-10-01", "end_date": "2026-10-31", "target_total": 10000,
        "items": [{"category": "Dining Out", "amount": 2000, "note": ""}]}


def test_plan_progress_counts_only_the_period():
    df = frame([
        {"date": "2026-09-30", "description": "Before", "amount": 5000, "type": "expense", "category": "Shopping"},
        {"date": "2026-10-05", "description": "Swiggy", "amount": 1500, "type": "expense", "category": "Dining Out"},
        {"date": "2026-10-10", "description": "Shoes", "amount": 3000, "type": "expense", "category": "Shopping"},
        {"date": "2026-10-11", "description": "Salary", "amount": 90000, "type": "income", "category": "Salary"},
        {"date": "2026-10-12", "description": "SIP", "amount": 4000, "type": "expense",
         "category": "Savings & Investments"},
    ])
    p = goals.plan_progress(df, PLAN, TODAY)
    assert p["spent"] == 4500 and p["status"] == "active" and p["days_left"] == 11
    assert p["projected"] == pytest.approx(4500 / 20 * 31)
    cats = {c["category"]: c for c in p["categories"]}
    assert cats["Dining Out"]["pct"] == 0.75 and cats["Shopping"]["unplanned"]


def test_alerts_at_80_and_100_percent():
    df = frame([{"date": "2026-10-05", "description": "Swiggy", "amount": 1700, "type": "expense",
                 "category": "Dining Out"},
                {"date": "2026-10-06", "description": "TV", "amount": 7000, "type": "expense",
                 "category": "Shopping"}])
    ids = {a["id"]: a["level"] for a in goals.alerts(df, [PLAN], {}, TODAY)}
    assert ids == {"plan1-total-warning": "warning", "plan1-Dining Out-warning": "warning"}

    df2 = frame([{"date": "2026-10-05", "description": "Swiggy", "amount": 2500, "type": "expense",
                  "category": "Dining Out"},
                 {"date": "2026-10-06", "description": "TV", "amount": 9000, "type": "expense",
                  "category": "Shopping"}])
    levels = {a["id"]: a["level"] for a in goals.alerts(df2, [PLAN], {"Shopping": 5000}, TODAY)}
    assert levels["plan1-total-exceeded"] == "exceeded"
    assert levels["plan1-Dining Out-exceeded"] == "exceeded"
    assert levels["budget-2026-10-Shopping"] == "exceeded"


def test_no_alerts_for_finished_or_upcoming_plans():
    df = frame([{"date": "2026-10-05", "description": "TV", "amount": 50000, "type": "expense", "category": "Shopping"}])
    assert goals.alerts(df, [PLAN], {}, date(2026, 11, 5)) == []
    assert goals.alerts(df, [PLAN], {}, date(2026, 9, 5)) == []


def test_penalty_scale():
    assert goals.penalty(100) == -1 and goals.penalty(1000) == -4 and goals.penalty(42000) == -10


def test_user_labels_drive_points():
    df = frame([
        {"date": "2026-10-01", "description": "Groceries", "amount": 800, "type": "expense", "category": "Groceries"},
        {"date": "2026-10-02", "description": "Gadget", "amount": 2000, "type": "expense", "category": "Shopping"},
        {"date": "2026-10-03", "description": "Groceries", "amount": 900, "type": "expense", "category": "Groceries"},
    ])
    df.loc[df["id"] == 1, "necessity"] = "Reasonable"
    df.loc[df["id"] == 2, "necessity"] = "Unnecessary"
    df.loc[df["id"] == 3, "necessity"] = "Reasonable"
    r = goals.rewards(df, [], {}, 20, date(2026, 10, 3))
    kinds = [e["kind"] for e in r["events"]]
    assert kinds.count("unnecessary") == 1 and kinds.count("clean_day") == 2
    assert r["total"] == 2 * goals.POINTS["clean_day"] + goals.penalty(2000)
    assert r["streak"] == 1


def test_finished_plan_scores():
    df = frame([{"date": "2026-10-05", "description": "Swiggy", "amount": 1500, "type": "expense",
                 "category": "Dining Out", "necessity": "Reasonable"}])
    r = goals.rewards(df, [PLAN], {}, 20, date(2026, 11, 2))
    plan_pts = [e["points"] for e in r["events"] if e["kind"] in ("plan", "category")]
    assert sorted(plan_pts) == [goals.POINTS["category_kept"], goals.POINTS["plan_kept"]]
    assert any(b["name"].endswith("Plan Keeper") and b["earned"] for b in r["badges"])


def test_demo_family_rewards_are_sane(tmp_path):
    store = BudgetStore(tmp_path / "g.db")
    store.add_many(sample_data.generate(today=date(2026, 10, 29)))
    r = goals.rewards(store.transactions(), [], {}, 20, date(2026, 10, 29))
    assert r["total"] > 0 and r["level"]["name"] and r["leaderboard"]
    assert r["leaderboard"][0]["share_unnecessary"] <= r["leaderboard"][-1]["share_unnecessary"]


# ---------------------------------------------------------------- API
@pytest.fixture
def client(tmp_path):
    s = BudgetStore(tmp_path / "goals.db")
    main.app.dependency_overrides[main.get_store] = lambda: s
    yield TestClient(main.app), s
    main.app.dependency_overrides.clear()


def test_plan_crud_and_validation(client):
    c, _ = client
    body = {"name": "Nov", "start_date": "2026-11-01", "end_date": "2026-11-30", "target_total": 50000,
            "items": [{"category": "Groceries", "amount": 8000}]}
    created = c.post("/api/plans", json=body).json()
    assert created["status"] in ("upcoming", "active", "finished") and created["items"][0]["category"] == "Groceries"
    pid = created["id"]
    assert c.put(f"/api/plans/{pid}", json={**body, "target_total": 45000}).json()["target_total"] == 45000
    assert len(c.get("/api/plans").json()) == 1
    assert c.post("/api/plans", json={**body, "end_date": "2026-10-01"}).status_code == 400
    assert c.post("/api/plans", json={**body, "items": [{"category": "Nope", "amount": 1}]}).status_code == 400
    assert c.post("/api/plans", json={**body, "items": [{"category": "Groceries", "amount": 1}] * 2}).status_code == 400
    assert c.delete(f"/api/plans/{pid}").json()["ok"]
    assert c.delete(f"/api/plans/{pid}").status_code == 404


def test_suggest_alerts_and_rewards_endpoints(client):
    c, _ = client
    c.post("/api/demo")
    sug = c.get("/api/plans/suggest", params={"start_date": "2026-11-01", "end_date": "2026-11-30"}).json()
    assert sug["items"] and sug["target_total"] == sum(i["amount"] for i in sug["items"])
    assert "alerts" in c.get("/api/alerts").json()
    r = c.get("/api/rewards").json()
    assert {"total", "level", "badges", "events", "leaderboard", "rules"} <= set(r)
