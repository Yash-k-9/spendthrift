"""Predict next month's spending, income and savings with Locally Weighted Regression.

For every category we have a monthly series y_0 .. y_{n-1}. LWR fits a local
line around x = n (next month) and reads off the prediction.

The bandwidth tau is chosen automatically by back-testing: for each past month
t we predict y_t using only months before t, and keep the tau with the lowest
mean absolute error (MAE). The same back-test gives the typical error, which
turns the prediction into a probability of meeting the savings goal.
"""

import math

import numpy as np
import pandas as pd

from . import analyzer
from .ml.lwr import lwr_predict

TAU_CANDIDATES = [0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
DEFAULT_TAU = 2.0
MIN_MONTHS = 3      # LWR needs a few points; with fewer we use the plain average


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def monthly_series(df: pd.DataFrame, upto: str):
    hist = df[df["month"] <= upto]
    months = sorted(hist["month"].unique())
    spend = analyzer.category_trend(hist).reindex(months, fill_value=0.0)
    income = hist[hist["type"] == "income"].groupby("month")["amount"].sum().reindex(months, fill_value=0.0)
    return months, spend, income


def predict_next(y, tau: float) -> float:
    y = np.asarray(y, dtype=float)
    if len(y) == 0:
        return 0.0
    if len(y) < MIN_MONTHS:
        return float(y.mean())
    pred = lwr_predict(np.arange(len(y)), y, len(y), tau)
    return float(np.clip(pred, 0, 2 * y.max()))  # a straight local line can overshoot - keep it sane


def backtest(spend: pd.DataFrame, income: pd.Series, tau: float) -> dict:
    """Walk-forward test: predict each month from the months before it."""
    n = len(spend)
    errs = {"lwr": [], "naive": [], "mean3": []}
    total_errors, income_errors = [], []
    for t in range(MIN_MONTHS, n):
        total_pred = total_actual = 0.0
        for cat in spend.columns:
            y = spend[cat].values
            pred = predict_next(y[:t], tau)
            errs["lwr"].append(abs(pred - y[t]))
            errs["naive"].append(abs(y[t - 1] - y[t]))            # "same as last month"
            errs["mean3"].append(abs(y[t - 3:t].mean() - y[t]))   # "average of last 3 months"
            total_pred += pred
            total_actual += y[t]
        total_errors.append(total_actual - total_pred)
        income_errors.append(income.values[t] - predict_next(income.values[:t], tau))
    return {
        "lwr_mae": float(np.mean(errs["lwr"])) if errs["lwr"] else None,
        "naive_mae": float(np.mean(errs["naive"])) if errs["naive"] else None,
        "mean3_mae": float(np.mean(errs["mean3"])) if errs["mean3"] else None,
        "tested_months": n - MIN_MONTHS if n > MIN_MONTHS else 0,
        "total_errors": total_errors,
        "income_errors": income_errors,
    }


def choose_tau(spend: pd.DataFrame, income: pd.Series) -> tuple[float, dict]:
    if len(spend) <= MIN_MONTHS:
        return DEFAULT_TAU, {}
    scores = {tau: backtest(spend, income, tau)["lwr_mae"] for tau in TAU_CANDIDATES}
    return min(scores, key=scores.get), scores


def forecast(df: pd.DataFrame, upto: str, savings_goal_pct: float, exclude_ids=()) -> dict | None:
    """Predict the month after `upto` using only data up to `upto`.

    exclude_ids: one-off purchases (found by k-Means) to leave out. A laptop bought
    once is not a trend, and keeping it would make LWR predict another laptop.
    """
    excluded = df[df["id"].isin(exclude_ids)]
    df = df[~df["id"].isin(exclude_ids)]
    months, spend, income = monthly_series(df, upto)
    if len(months) < 2:
        return None
    tau, tau_scores = choose_tau(spend, income)
    bt = backtest(spend, income, tau)

    rows = []
    for cat in spend.columns:
        y = spend[cat].values
        pred = predict_next(y, tau)
        avg3 = float(y[-3:].mean())
        rows.append({"category": cat, "last_month": float(y[-1]), "avg_3_months": avg3, "predicted": pred,
                     "change_pct": (pred / avg3 - 1) * 100 if avg3 else 0.0})
    categories = pd.DataFrame(rows).sort_values("predicted", ascending=False).reset_index(drop=True)

    income_pred = predict_next(income.values, tau)
    spending_pred = float(categories["predicted"].sum())
    savings_pred = income_pred - spending_pred

    # Uncertainty from the back-test errors (fallback: 15% of spending).
    errors = np.array(bt["total_errors"]) - np.array(bt["income_errors"]) if bt["total_errors"] else []
    sigma = float(np.sqrt(np.mean(np.square(errors)))) if len(errors) >= 2 else 0.15 * spending_pred
    sigma = max(sigma, 0.03 * spending_pred, 1.0)
    allowed_spending = income_pred * (1 - savings_goal_pct / 100)
    prob_goal = _normal_cdf((allowed_spending - spending_pred) / sigma)

    next_month = str(pd.Period(upto) + 1)
    actual = None
    if next_month in set(df["month"]):
        s = analyzer.monthly_summary(df, next_month)
        by_cat = analyzer.category_breakdown(df, next_month).set_index("category")["amount"]
        categories["actual"] = categories["category"].map(by_cat).fillna(0.0)
        actual = {"income": s["income"], "spending": s["spending"], "savings_rate_pct": s["savings_rate_pct"]}

    return {
        "next_month": next_month,
        "history_months": months,
        "spend_history": spend,
        "income_history": income,
        "categories": categories,
        "income_pred": income_pred,
        "spending_pred": spending_pred,
        "savings_pred": savings_pred,
        "savings_rate_pred": savings_pred / income_pred * 100 if income_pred else 0.0,
        "spending_range": (spending_pred - 1.28 * sigma, spending_pred + 1.28 * sigma),  # ~80% interval
        "prob_goal": prob_goal,
        "tau": tau,
        "tau_scores": tau_scores,
        "backtest": bt,
        "actual": actual,
        "excluded": excluded[excluded["month"] <= upto],
    }
