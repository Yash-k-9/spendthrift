"""Discover spending patterns with k-Means clustering.

Each expense becomes a point with three features:
  log_amount   log(1 + amount)                         - how big it is
  per_month    times this merchant is paid in a month  - how often
  recurrence   share of months this merchant appears   - how regular
Features are standardised (z-scores) so no single one dominates the distance.
k-Means groups similar expenses; each cluster is then named from its centroid,
e.g. "Fixed monthly bills" or "Frequent small spends".
"""

import numpy as np
import pandas as pd

from . import analyzer
from .ml.kmeans import elbow, kmeans

FEATURES = ["log_amount", "per_month", "recurrence"]


def pattern_features(df: pd.DataFrame) -> pd.DataFrame:
    exp = df[(df["type"] == "expense") & (df["category"] != analyzer.SAVINGS_CATEGORY)].copy()
    if exp.empty:
        return exp
    total_months = df["month"].nunique()
    exp["merchant"] = exp["description"].str.lower().str.strip()
    g = exp.groupby("merchant")
    active = g["month"].transform("nunique")
    exp["log_amount"] = np.log1p(exp["amount"])
    exp["per_month"] = g["amount"].transform("count") / active
    exp["recurrence"] = active / total_months
    return exp


ONE_OFF = "Large one-off purchases"


def _name(amount: float, per_month: float, recurrence: float, median_amount: float) -> str:
    if per_month >= 2.5:
        return "Frequent small spends" if amount < median_amount else "Frequent spends"
    if recurrence >= 0.6:
        if per_month <= 1.3:
            return "Fixed monthly bills"
        return "Regular household spends" if amount >= median_amount else "Regular small spends"
    return ONE_OFF if amount >= median_amount else "Occasional spends"


def find_patterns(df: pd.DataFrame, k: int = 4) -> dict | None:
    exp = pattern_features(df)
    if len(exp) < max(k * 3, 10):
        return None
    raw = exp[FEATURES].to_numpy(dtype=float)
    mean, std = raw.mean(axis=0), raw.std(axis=0)
    X = (raw - mean) / np.where(std == 0, 1, std)

    _, labels, sse, iterations = kmeans(X, k)
    exp["cluster"] = labels
    median_amount = float(exp["amount"].median())

    summary = []
    for c in range(k):
        pts = exp[exp["cluster"] == c]
        if pts.empty:
            continue
        typical = float(np.expm1(pts["log_amount"].mean()))
        summary.append({
            "cluster": c,
            "name": _name(typical, pts["per_month"].mean(), pts["recurrence"].mean(), median_amount),
            "transactions": len(pts),
            "typical_amount": typical,
            "per_month": float(pts["per_month"].mean()),
            "recurrence_pct": float(pts["recurrence"].mean() * 100),
            "total": float(pts["amount"].sum()),
            "examples": ", ".join(pts["description"].value_counts().index[:4]),
        })
    # Make names unique if two clusters got the same one.
    seen = {}
    for s in sorted(summary, key=lambda s: -s["total"]):
        seen[s["name"]] = seen.get(s["name"], 0) + 1
        if seen[s["name"]] > 1:
            s["name"] += f" ({seen[s['name']]})"
    names = {s["cluster"]: s["name"] for s in summary}
    exp["pattern"] = exp["cluster"].map(names)

    k_values = list(range(1, 9))
    return {
        "one_off_ids": set(exp.loc[exp["pattern"].str.startswith(ONE_OFF), "id"]),
        "transactions": exp,
        "summary": pd.DataFrame(summary).sort_values("total", ascending=False).reset_index(drop=True),
        "sse": sse,
        "iterations": iterations,
        "elbow": {"k": k_values, "sse": elbow(X, k_values)},
    }
