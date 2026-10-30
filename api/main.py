"""AI-Based Family Budget Planner - FastAPI backend.

Serves a JSON API under /api and the HTML/CSS/JS frontend (frontend/) at /.
All the machine learning lives in the `budget` package; this module only turns
its pandas results into JSON.

Run with:  uvicorn api.main:app --reload
Then open http://localhost:8000  (interactive API docs at /docs)
"""

import hmac
import io
import json
import os
import secrets
import socket
from datetime import date as Date
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from budget import (analyzer, anomalies, categorizer, forecaster, goals, necessity, patterns, planner, sample_data,
                    sms, sms_demo)
from budget.categorizer import ALL_CATEGORIES, EXPENSE_CATEGORIES, INCOME_CATEGORIES, KNNCategorizer
from budget.storage import ENV_FILE, BudgetStore, DuplicateTransaction, load_dotenv

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Family Budget Planner API",
              description="Six from-scratch ML algorithms (k-NN, LWR, ID3, k-Means, EM, GA) for family budgeting.")


# ---------------------------------------------------------------- dependencies & helpers
@lru_cache(maxsize=1)
def get_store() -> BudgetStore:
    return BudgetStore()


@lru_cache(maxsize=4)
def get_categorizer(corrections: tuple) -> KNNCategorizer:
    return KNNCategorizer(list(corrections))


@lru_cache(maxsize=1)
def knn_evaluation() -> dict:
    return categorizer.evaluate()


def knn_for(store: BudgetStore) -> KNNCategorizer:
    return get_categorizer(tuple(store.category_corrections()))


def records(df: pd.DataFrame, columns: list[str] | None = None) -> list[dict]:
    """DataFrame -> JSON-safe list of dicts (dates as YYYY-MM-DD, NaN as null)."""
    if df is None or df.empty:
        return []
    out = df[columns].copy() if columns else df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    return json.loads(out.to_json(orient="records"))


def goal_of(store: BudgetStore) -> float:
    return float(store.get_setting("savings_goal_pct"))


def load(store: BudgetStore, month: str | None):
    """Transactions plus the month to analyse (defaults to the latest)."""
    df = store.transactions()
    if df.empty:
        raise HTTPException(404, "No transactions yet. Add some, or load the demo family.")
    month_list = analyzer.months(df)
    if month is None:
        month = month_list[0]
    elif month not in month_list:
        raise HTTPException(404, f"No transactions in {month}.")
    return df, month, month_list


def one_off_ids(df: pd.DataFrame) -> set:
    result = patterns.find_patterns(df, 4)
    return result["one_off_ids"] if result else set()


# ---------------------------------------------------------------- meta & settings
class Settings(BaseModel):
    currency: str = Field(min_length=1, max_length=4)
    savings_goal_pct: int = Field(ge=5, le=60)
    family_size: int = Field(ge=1, le=20)


def read_settings(store: BudgetStore) -> dict:
    return {"currency": store.get_setting("currency"),
            "savings_goal_pct": int(float(store.get_setting("savings_goal_pct"))),
            "family_size": int(store.get_setting("family_size"))}


@app.get("/api/meta")
def meta(store: BudgetStore = Depends(get_store)):
    df = store.transactions()
    return {
        "settings": read_settings(store),
        "months": analyzer.months(df),
        "categories": {"expense": EXPENSE_CATEGORIES, "income": INCOME_CATEGORIES, "all": ALL_CATEGORIES},
        "savings_category": analyzer.SAVINGS_CATEGORY,
        "transaction_count": int(len(df)),
        "legacy_plaintext_rows": store.legacy_rows,
    }


@app.put("/api/settings")
def save_settings(settings: Settings, store: BudgetStore = Depends(get_store)):
    for key, value in settings.model_dump().items():
        store.set_setting(key, value)
    return read_settings(store)


@app.post("/api/demo")
def load_demo(store: BudgetStore = Depends(get_store)):
    store.clear_transactions()
    return {"added": store.add_many(sample_data.generate())}


@app.delete("/api/transactions")
def clear_transactions(store: BudgetStore = Depends(get_store)):
    store.clear_transactions()
    return {"ok": True}


# ---------------------------------------------------------------- dashboard
@app.get("/api/dashboard")
def dashboard(month: str | None = None, store: BudgetStore = Depends(get_store)):
    df, month, month_list = load(store, month)
    prev = [m for m in month_list if m < month]
    return {
        "month": month,
        "goal": goal_of(store),
        "summary": analyzer.monthly_summary(df, month),
        "previous": analyzer.monthly_summary(df, prev[0]) if prev else None,
        "breakdown": records(analyzer.category_breakdown(df, month)),
        "split": analyzer.needs_wants_split(df, month),
        "trend": records(analyzer.monthly_trend(df)),
    }


# ---------------------------------------------------------------- insights
@app.get("/api/insights")
def insights(month: str | None = None, store: BudgetStore = Depends(get_store)):
    df, month, _ = load(store, month)
    budgets, goal = store.budgets(), goal_of(store)

    classified, _ = necessity.classify_month(df, month, budgets)
    unnecessary = None
    if not classified.empty:
        flagged = classified[classified["prediction"] == "Unnecessary"].sort_values("amount", ascending=False)
        total = float(classified["amount"].sum())
        unnecessary = {
            "total": float(flagged["amount"].sum()),
            "count": int(len(flagged)),
            "of": int(len(classified)),
            "share_pct": float(flagged["amount"].sum() / total * 100) if total else 0.0,
            "rows": records(flagged, ["id", "date", "description", "category", "amount", "reason"]),
        }

    anomaly = anomalies.detect(df, month)
    return {
        "month": month,
        "unnecessary": unnecessary,
        "anomalies": None if anomaly is None else records(anomaly["flagged"]),
        "anomaly_min_transactions": anomalies.MIN_TRANSACTIONS,
        "issues": analyzer.detect_issues(df, month, budgets, goal),
        "tips": analyzer.recommendations(df, month, budgets, goal),
    }


# ---------------------------------------------------------------- predictions
def _plan(fc: dict, target: float) -> dict:
    cats = fc["categories"]
    spend_pred = dict(zip(cats["category"], cats["predicted"]))
    usual = dict(zip(cats["category"], cats["avg_3_months"]))
    return planner.optimise_plan(spend_pred, usual, fc["income_pred"], float(target))


def _default_target(fc: dict, goal: float) -> int:
    return int(min(60, max(goal, round(fc["savings_rate_pred"] + 5))))


@app.get("/api/predictions")
def predictions(month: str | None = None, target: int | None = Query(None, ge=5, le=60),
                store: BudgetStore = Depends(get_store)):
    df, month, _ = load(store, month)
    goal = goal_of(store)
    fc = forecaster.forecast(df, month, goal, one_off_ids(df))
    if fc is None:
        return {"available": False, "month": month}

    target = target if target is not None else _default_target(fc, goal)
    plan = _plan(fc, target)
    cats = fc["categories"]
    hist_total = fc["spend_history"].sum(axis=1)
    rising = cats[(cats["change_pct"] > 15) & (cats["predicted"] > 1000)]
    return {
        "available": True,
        "month": month,
        "goal": goal,
        "next_month": fc["next_month"],
        "tau": fc["tau"],
        "excluded_count": int(len(fc["excluded"])),
        "income_pred": fc["income_pred"],
        "spending_pred": fc["spending_pred"],
        "spending_range": list(fc["spending_range"]),
        "savings_rate_pred": fc["savings_rate_pred"],
        "prob_goal": fc["prob_goal"],
        "actual": fc["actual"],
        "history": {"months": list(hist_total.index), "spending": [float(v) for v in hist_total.values],
                    "income": [float(v) for v in fc["income_history"].values]},
        "categories": records(cats),
        "rising": records(rising, ["category", "predicted", "change_pct"]),
        "plan": {
            "target": target,
            "needed": plan["needed"],
            "saved": plan["saved"],
            "reached": plan["reached"],
            "max_possible": plan["max_possible"],
            "new_savings_rate": plan["new_savings_rate"],
            "rows": records(plan["plan"]),
        },
    }


class ApplyPlan(BaseModel):
    month: str
    target: int = Field(ge=5, le=60)


@app.post("/api/budgets/apply-plan")
def apply_plan(body: ApplyPlan, store: BudgetStore = Depends(get_store)):
    df, month, _ = load(store, body.month)
    fc = forecaster.forecast(df, month, goal_of(store), one_off_ids(df))
    if fc is None:
        raise HTTPException(400, "Predictions need at least 2 months of data.")
    plan = _plan(fc, body.target)["plan"]
    for _, r in plan.iterrows():
        store.set_budget(r["category"], round(r["new_budget"] / 100) * 100)
    return {"updated": int(len(plan)), "budgets": store.budgets()}


# ---------------------------------------------------------------- patterns
@app.get("/api/patterns")
def spending_patterns(month: str | None = None, k: int = Query(4, ge=2, le=7),
                      store: BudgetStore = Depends(get_store)):
    df, month, _ = load(store, month)
    pr = patterns.find_patterns(df, k)
    if pr is None:
        return {"available": False, "month": month}
    tx = pr["transactions"]
    month_totals = tx[tx["month"] == month].groupby("pattern")["amount"].sum()
    summary = pr["summary"].assign(this_month=lambda s: s["name"].map(month_totals).fillna(0.0))
    return {
        "available": True,
        "month": month,
        "k": k,
        "summary": records(summary),
        "points": records(tx, ["description", "per_month", "amount", "pattern"]),
    }


# ---------------------------------------------------------------- budgets
class BudgetUpdate(BaseModel):
    budgets: dict[str, float]


@app.get("/api/budgets")
def get_budgets(month: str | None = None, store: BudgetStore = Depends(get_store)):
    df, month, _ = load(store, month)
    budgets = store.budgets()
    b = analyzer.category_breakdown(df, month)
    spent = dict(zip(b["category"], b["amount"]))
    suggested = analyzer.suggest_budgets(df, month)
    cats = [c for c in EXPENSE_CATEGORIES if c != analyzer.SAVINGS_CATEGORY]
    rows = [{"category": c, "type": EXPENSE_CATEGORIES[c], "spent": float(spent.get(c, 0.0)),
             "suggested": float(suggested.get(c, 0.0)), "budget": float(budgets.get(c, 0.0))} for c in cats]
    active = {c: l for c, l in budgets.items() if l > 0}
    progress = [{"category": c, "spent": float(spent.get(c, 0.0)), "limit": l, "pct": spent.get(c, 0.0) / l}
                for c, l in active.items()]
    progress.sort(key=lambda p: -p["pct"])
    return {"month": month, "rows": rows, "progress": progress}


@app.put("/api/budgets")
def save_budgets(body: BudgetUpdate, store: BudgetStore = Depends(get_store)):
    existing = store.budgets()
    for cat, limit in body.budgets.items():
        if cat not in EXPENSE_CATEGORIES:
            raise HTTPException(400, f"Unknown category: {cat}")
        if limit < 0:
            raise HTTPException(400, "Budgets can't be negative.")
        if limit > 0 or cat in existing:
            store.set_budget(cat, limit)
    return store.budgets()


@app.post("/api/budgets/suggested")
def use_suggested(month: str | None = None, store: BudgetStore = Depends(get_store)):
    df, month, _ = load(store, month)
    for cat, limit in analyzer.suggest_budgets(df, month).items():
        if cat in EXPENSE_CATEGORIES and cat != analyzer.SAVINGS_CATEGORY and limit > 0:
            store.set_budget(cat, limit)
    return store.budgets()


# ---------------------------------------------------------------- add / import
class NewTransaction(BaseModel):
    type: Literal["expense", "income"]
    description: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0)
    date: Date
    member: str = "Family"
    category: str | None = None   # None = auto-detect with k-NN


class ImportRow(BaseModel):
    date: str
    description: str
    amount: float = Field(gt=0)
    type: Literal["expense", "income"]
    category: str
    member: str = "Family"
    source: str = "knn"


@app.get("/api/knn/predict")
def knn_predict(description: str, type: Literal["expense", "income"] = "expense",
                store: BudgetStore = Depends(get_store)):
    pred = knn_for(store).predict(description, type)
    pred["neighbours"] = [{"description": d, "category": c, "similarity": s} for d, c, s in pred["neighbours"]]
    return pred


@app.post("/api/transactions", status_code=201)
def add_transaction(t: NewTransaction, store: BudgetStore = Depends(get_store)):
    if not t.description.strip():
        raise HTTPException(400, "Enter a description.")
    pred = None
    if t.category:
        if t.category not in ALL_CATEGORIES:
            raise HTTPException(400, f"Unknown category: {t.category}")
        category, source = t.category, "manual"
    else:
        pred = knn_for(store).predict(t.description, t.type)
        category, source = pred["category"], "knn"
    txn_id = store.add_transaction(t.date, t.description, t.amount, t.type, category, t.member.strip() or "Family",
                                   source)
    return {"id": txn_id, "category": category, "source": source,
            "confidence": pred["confidence"] if pred else None,
            "needs_review": pred["needs_review"] if pred else False}


@app.post("/api/import/preview")
async def import_preview(file: UploadFile = File(...), store: BudgetStore = Depends(get_store)):
    try:
        raw = pd.read_csv(io.BytesIO(await file.read()))
        raw.columns = [c.strip().lower() for c in raw.columns]
        missing = {"date", "description", "amount"} - set(raw.columns)
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        raw["date"] = pd.to_datetime(raw["date"], dayfirst=True).dt.strftime("%Y-%m-%d")
        raw["amount"] = pd.to_numeric(raw["amount"])
        if "type" not in raw.columns:
            raw["type"] = raw["amount"].apply(lambda a: "expense" if a < 0 else "income")
        raw["type"] = raw["type"].astype(str).str.lower().str.strip()
        raw["amount"] = raw["amount"].abs()
        raw["member"] = raw["member"].fillna("Family").astype(str) if "member" in raw.columns else "Family"
        raw["description"] = raw["description"].astype(str)
        raw = raw[(raw["amount"] > 0) & raw["type"].isin(["income", "expense"])].reset_index(drop=True)
    except Exception as e:
        raise HTTPException(400, f"Couldn't read that file: {e}")
    knn = knn_for(store)
    preds = [knn.predict(d, t) for d, t in zip(raw["description"], raw["type"])]
    raw["category"] = [p["category"] for p in preds]
    raw["confidence"] = [p["confidence"] for p in preds]
    raw["needs_review"] = [p["needs_review"] for p in preds]
    raw["source"] = "knn"
    return {"rows": records(raw, ["date", "description", "amount", "type", "category", "member", "source",
                                  "confidence", "needs_review"]),
            "unsure": int(sum(p["needs_review"] for p in preds))}


@app.post("/api/import", status_code=201)
def import_rows(rows: list[ImportRow], store: BudgetStore = Depends(get_store)):
    for r in rows:
        if r.category not in ALL_CATEGORIES:
            raise HTTPException(400, f"Unknown category: {r.category}")
    return {"added": store.add_many([r.model_dump() for r in rows])}


# ---------------------------------------------------------------- transactions
class TransactionPatch(BaseModel):
    category: str | None = None
    necessity: Literal["", "Reasonable", "Unnecessary"] | None = None


def filtered(store: BudgetStore, month: str | None, category: str | None, q: str | None) -> pd.DataFrame:
    df = store.transactions()
    if df.empty:
        return df
    if month:
        df = df[df["month"] == month]
    if category:
        df = df[df["category"] == category]
    if q:
        df = df[df["description"].str.contains(q, case=False, regex=False)]
    return df


TX_COLUMNS = ["id", "date", "description", "amount", "type", "category", "necessity", "member", "source"]


@app.get("/api/transactions")
def list_transactions(month: str | None = None, category: str | None = None, q: str | None = None,
                      store: BudgetStore = Depends(get_store)):
    all_df = store.transactions()
    view = filtered(store, month, category, q)
    return {"rows": records(view, TX_COLUMNS),
            "categories": sorted(all_df["category"].unique()) if not all_df.empty else []}


@app.get("/api/transactions/export.csv")
def export_transactions(month: str | None = None, category: str | None = None, q: str | None = None,
                        store: BudgetStore = Depends(get_store)):
    view = filtered(store, month, category, q)
    csv = view[TX_COLUMNS].assign(date=view["date"].dt.strftime("%Y-%m-%d")).to_csv(index=False) \
        if not view.empty else ",".join(TX_COLUMNS) + "\n"
    return StreamingResponse(iter([csv]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=transactions.csv"})


@app.patch("/api/transactions/{txn_id}")
def update_transaction(txn_id: int, patch: TransactionPatch, store: BudgetStore = Depends(get_store)):
    found = True
    if patch.category is not None:
        if patch.category not in ALL_CATEGORIES:
            raise HTTPException(400, f"Unknown category: {patch.category}")
        found = store.update_category(txn_id, patch.category, source="manual")
    if patch.necessity is not None:
        found = store.set_necessity(txn_id, patch.necessity) and found
    if not found:
        raise HTTPException(404, "Transaction not found")
    return {"ok": True}


@app.delete("/api/transactions/{txn_id}")
def delete_transaction(txn_id: int, store: BudgetStore = Depends(get_store)):
    if not store.delete_transaction(txn_id):
        raise HTTPException(404, "Transaction not found")
    return {"ok": True}


# ---------------------------------------------------------------- models
@app.get("/api/models")
def models(store: BudgetStore = Depends(get_store)):
    knn = knn_for(store)
    ev = knn_evaluation()
    out = {"knn": {
        "training_examples": knn.n_seed + knn.n_corrections,
        "corrections": knn.n_corrections,
        "accuracy_phrasing": ev["unseen_phrasing"][5],
        "accuracy_merchant": ev["unseen_merchant"][5],
        "curve": [{"k": k, "phrasing": ev["unseen_phrasing"][k], "merchant": ev["unseen_merchant"][k]}
                  for k in ev["unseen_phrasing"]],
    }}
    df = store.transactions()
    if df.empty:
        return out

    latest, goal = analyzer.months(df)[0], goal_of(store)
    pr = patterns.find_patterns(df, 4)
    fc = forecaster.forecast(df, latest, goal, pr["one_off_ids"] if pr else set())
    if fc:
        out["lwr"] = {"min_months": forecaster.MIN_MONTHS,
                      "tau_scores": [{"tau": t, "mae": m} for t, m in fc["tau_scores"].items()],
                      "backtest": {k: v for k, v in fc["backtest"].items() if not k.endswith("_errors")}}
        plan = _plan(fc, _default_target(fc, goal))
        out["ga"] = {"history": [float(h) for h in plan["history"]], "target": _default_target(fc, goal)}

    feats = necessity.expense_features(df, store.budgets())
    tree = necessity.train_tree(feats)
    root = tree.tree
    out["id3"] = {
        "depth": tree.depth(),
        "rules": tree.rules(),
        "user_labels": int(feats["necessity"].notna().sum()) if "necessity" in feats else 0,
        "user_label_weight": necessity.USER_LABEL_WEIGHT,
        "root": {"attribute": root["attribute"], "gain": root["gain"]} if "attribute" in root else None,
    }
    if pr:
        out["kmeans"] = {"elbow": [{"k": k, "sse": float(s)} for k, s in zip(pr["elbow"]["k"], pr["elbow"]["sse"])]}

    anomaly = anomalies.detect(df, latest)
    if anomaly:
        out["em"] = {"iterations": anomaly["iterations"],
                     "log_likelihood_history": [float(v) for v in anomaly["log_likelihood_history"]],
                     "log_likelihoods": [float(v) for v in anomaly["all"]["log_likelihood"]],
                     "threshold": anomaly["threshold"]}
    return out


# ---------------------------------------------------------------- spending plans, alerts & rewards
class PlanItem(BaseModel):
    category: str
    amount: float = Field(ge=0)
    note: str = Field("", max_length=120)


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    start_date: Date
    end_date: Date
    target_total: float = Field(ge=0)
    items: list[PlanItem] = []


def _check_plan(plan: PlanIn):
    if plan.end_date < plan.start_date:
        raise HTTPException(400, "The end date must be on or after the start date.")
    for item in plan.items:
        if item.category not in EXPENSE_CATEGORIES:
            raise HTTPException(400, f"Unknown category: {item.category}")
    if len({i.category for i in plan.items}) != len(plan.items):
        raise HTTPException(400, "Each category can appear only once in a plan.")


@app.get("/api/plans")
def list_plans(store: BudgetStore = Depends(get_store)):
    df = store.transactions()
    return [goals.plan_progress(df, p) for p in store.plans()]


@app.get("/api/plans/suggest", summary="Suggested planned amounts for a period, from recent spending")
def suggest_plan(start_date: Date, end_date: Date, store: BudgetStore = Depends(get_store)):
    df = store.transactions()
    if df.empty:
        return {"items": [], "target_total": 0}
    scale = ((end_date - start_date).days + 1) / 30.4
    monthly = analyzer.suggest_budgets(df, analyzer.months(df)[0])
    items = [{"category": c, "amount": float(round(v * scale / 100) * 100), "note": ""}
             for c, v in sorted(monthly.items(), key=lambda kv: -kv[1])
             if c in EXPENSE_CATEGORIES and c != analyzer.SAVINGS_CATEGORY and v * scale >= 100]
    return {"items": items, "target_total": float(sum(i["amount"] for i in items))}


@app.post("/api/plans", status_code=201)
def create_plan(plan: PlanIn, store: BudgetStore = Depends(get_store)):
    _check_plan(plan)
    plan_id = store.save_plan(plan.name, plan.start_date, plan.end_date, plan.target_total,
                              [i.model_dump() for i in plan.items])
    return goals.plan_progress(store.transactions(), store.plan(plan_id))


@app.put("/api/plans/{plan_id}")
def update_plan(plan_id: int, plan: PlanIn, store: BudgetStore = Depends(get_store)):
    _check_plan(plan)
    try:
        store.save_plan(plan.name, plan.start_date, plan.end_date, plan.target_total,
                        [i.model_dump() for i in plan.items], plan_id=plan_id)
    except KeyError:
        raise HTTPException(404, "Plan not found")
    return goals.plan_progress(store.transactions(), store.plan(plan_id))


@app.delete("/api/plans/{plan_id}")
def delete_plan(plan_id: int, store: BudgetStore = Depends(get_store)):
    if not store.delete_plan(plan_id):
        raise HTTPException(404, "Plan not found")
    return {"ok": True}


@app.get("/api/alerts", summary="Over-target warnings for active plans and this month's budgets")
def get_alerts(store: BudgetStore = Depends(get_store)):
    return {"alerts": goals.alerts(store.transactions(), store.plans(), store.budgets(),
                                   currency=store.get_setting("currency"))}


@app.get("/api/rewards", summary="Points, level, streaks, badges and the family leaderboard")
def get_rewards(store: BudgetStore = Depends(get_store)):
    return goals.rewards(store.transactions(), store.plans(), store.budgets(), goal_of(store))


# ---------------------------------------------------------------- SMS capture
class SmsIn(BaseModel):
    sender: str = Field(min_length=1, max_length=40, description="SMS sender ID, e.g. VM-HDFCBK")
    body: str = Field(min_length=1, max_length=1000)
    received_at: datetime | None = None


@lru_cache(maxsize=1)
def sms_token() -> str:
    """Shared secret the phone sends in the X-SMS-Token header. Generated into .env on first use."""
    load_dotenv()
    token = os.environ.get("SMS_TOKEN")
    if not token:
        token = secrets.token_urlsafe(24)
        with ENV_FILE.open("a", encoding="utf-8") as f:
            f.write("\n# Secret your phone sends with each forwarded SMS (header X-SMS-Token).\n"
                    f"SMS_TOKEN={token}\n")
        os.environ["SMS_TOKEN"] = token
    return token


def ingest_sms(store: BudgetStore, msg: SmsIn) -> dict:
    """parse -> k-NN categorize -> encrypt + chain + sign -> store. Never raises for bad messages."""
    parsed = sms.parse(msg.sender, msg.body, msg.received_at)
    result = {"sender": msg.sender, "body": msg.body, **parsed}
    if not parsed["ok"]:
        return {**result, "stored": False}
    t = parsed["transaction"]
    pred = knn_for(store).predict(t["description"], t["type"])
    t.update(category=pred["category"], confidence=pred["confidence"], needs_review=pred["needs_review"])
    try:
        t["id"] = store.add_transaction(
            t["date"], t["description"], t["amount"], t["type"], t["category"], source="knn", channel="sms",
            sms={"sender": msg.sender, "body": msg.body, "bank": t["bank"], "account": t["account"],
                 "reference": t["reference"]},
            dedupe_text=sms.dedupe_key(msg.sender, msg.body))
    except DuplicateTransaction:
        return {**result, "stored": False, "reason": "Duplicate: this SMS was already recorded."}
    return {**result, "stored": True}


@app.post("/api/sms", summary="Receive a forwarded bank SMS (needs the X-SMS-Token header)")
def receive_sms(msg: SmsIn, x_sms_token: str | None = Header(None), store: BudgetStore = Depends(get_store)):
    if not x_sms_token or not hmac.compare_digest(x_sms_token, sms_token()):
        raise HTTPException(401, "Missing or wrong X-SMS-Token.")
    return ingest_sms(store, msg)


@app.post("/api/sms/parse", summary="Preview how an SMS would be parsed, without storing it")
def preview_sms(msg: SmsIn, store: BudgetStore = Depends(get_store)):
    parsed = sms.parse(msg.sender, msg.body, msg.received_at)
    if parsed["ok"]:
        t = parsed["transaction"]
        pred = knn_for(store).predict(t["description"], t["type"])
        t.update(category=pred["category"], confidence=pred["confidence"], needs_review=pred["needs_review"])
        t["duplicate"] = store.is_duplicate(sms.dedupe_key(msg.sender, msg.body))
    return parsed


@app.post("/api/sms/demo", summary="Demo mode: simulate bank SMS through the full pipeline")
def demo_sms(count: int = Query(6, ge=1, le=30), store: BudgetStore = Depends(get_store)):
    results = [ingest_sms(store, SmsIn(**m)) for m in sms_demo.generate(count)]
    return {"results": results, "stored": sum(r["stored"] for r in results)}


@app.get("/api/sms/recent")
def recent_sms(limit: int = Query(20, ge=1, le=100), store: BudgetStore = Depends(get_store)):
    rows = store.sms_transactions(limit)
    return {"rows": [{k: r.get(k) for k in ("id", "date", "description", "amount", "type", "category", "source")}
                     | {"bank": (r.get("sms") or {}).get("bank"), "account": (r.get("sms") or {}).get("account"),
                        "body": (r.get("sms") or {}).get("body")} for r in rows]}


# ---------------------------------------------------------------- security & network
@app.get("/api/security")
def security(store: BudgetStore = Depends(get_store)):
    return {
        "integrity": store.verify_integrity(),
        "keys": store.vault.fingerprints(),
        "algorithms": {"encryption": "AES-256-GCM (random 96-bit nonce per record)",
                       "chain": "SHA-256 hash chain", "signature": "Ed25519",
                       "dedupe": "HMAC-SHA256", "key_derivation": "HKDF-SHA256 from LEDGER_KEY"},
        "legacy_plaintext_rows": store.legacy_rows,
    }


def lan_addresses() -> list[str]:
    """This computer's private IPv4 addresses (what a phone on the same Wi-Fi can reach)."""
    found = []
    try:  # the address used for outgoing traffic; connecting a UDP socket sends no packets
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        found += [i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    private = [ip for ip in dict.fromkeys(found)
               if ip.startswith(("192.168.", "10.")) or (ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31)]
    return private


@app.get("/api/network")
def network(request: Request):
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    ips = lan_addresses()
    return {
        "port": port,
        "addresses": ips,
        "app_urls": [f"http://{ip}:{port}" for ip in ips],
        "sms_urls": [f"http://{ip}:{port}/api/sms" for ip in ips],
        "opened_via": request.url.hostname,
        "token_location": ".env (SMS_TOKEN)",
        "token_ready": bool(sms_token()),
    }


# ---------------------------------------------------------------- frontend (mounted last so /api wins)
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
