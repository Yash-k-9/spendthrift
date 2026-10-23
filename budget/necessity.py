"""Classify each expense as Reasonable or Unnecessary with an ID3 decision tree.

Every expense is described by five categorical attributes:
  category_type  need / want                         (50/30/20 bucket of its category)
  amount_level   low / normal / high / very_high     (vs. the family's usual amount in that category)
  frequency      rare / regular / frequent           (purchases in that category that month)
  day_type       weekday / weekend
  budget_status  within / over                       (category total vs. budget, or vs. usual spend)

Training data = built-in expert examples + the family's own labels (weighted 3x),
so the tree adapts to what each family considers necessary.
"""

import numpy as np
import pandas as pd

from . import analyzer
from .categorizer import EXPENSE_CATEGORIES
from .ml.id3 import ID3DecisionTree
from .training_data import NECESSITY_ATTRIBUTES, expert_necessity_examples

USER_LABEL_WEIGHT = 3.0
NICE = {
    "category_type": "category is a", "amount_level": "amount is", "frequency": "purchases are",
    "day_type": "bought on a", "budget_status": "category is",
}


def expense_features(df: pd.DataFrame, budgets: dict[str, float]) -> pd.DataFrame:
    exp = df[(df["type"] == "expense") & (df["category"] != analyzer.SAVINGS_CATEGORY)].copy()
    if exp.empty:
        return exp
    exp["category_type"] = exp["category"].map(EXPENSE_CATEGORIES).fillna("want")

    ratio = exp["amount"] / exp.groupby("category")["amount"].transform("median")
    exp["amount_ratio"] = ratio
    exp["amount_level"] = pd.cut(ratio, [-np.inf, 0.75, 1.5, 3.0, np.inf],
                                 labels=["low", "normal", "high", "very_high"]).astype(str)

    count = exp.groupby(["month", "category"])["amount"].transform("count")
    exp["frequency"] = np.select([count <= 2, count <= 6], ["rare", "regular"], "frequent")
    exp["day_type"] = np.where(exp["date"].dt.dayofweek >= 5, "weekend", "weekday")

    totals = exp.groupby(["month", "category"])["amount"].sum()
    over = {}
    for month in exp["month"].unique():
        usual = analyzer.category_baseline(df, month)
        for (m, cat), total in totals[totals.index.get_level_values(0) == month].items():
            limit = budgets.get(cat) or (usual.get(cat, 0) * 1.2) or np.inf
            over[(m, cat)] = "over" if total > limit else "within"
    exp["budget_status"] = [over[(m, c)] for m, c in zip(exp["month"], exp["category"])]
    return exp


def train_tree(features: pd.DataFrame) -> ID3DecisionTree:
    rows, labels = expert_necessity_examples()
    weights = [1.0] * len(rows)
    labelled = features[features["necessity"].notna()] if "necessity" in features else features.iloc[0:0]
    for _, r in labelled.iterrows():
        rows.append({a: r[a] for a in NECESSITY_ATTRIBUTES})
        labels.append(r["necessity"])
        weights.append(USER_LABEL_WEIGHT)
    return ID3DecisionTree().fit(rows, labels, NECESSITY_ATTRIBUTES, weights)


def explain(path) -> str:
    return " → ".join(f"{NICE[a]} {v.replace('_', ' ')}" for a, v in path)


def classify_month(df: pd.DataFrame, month: str, budgets: dict[str, float]):
    """Returns (DataFrame of the month's expenses with prediction + reason, trained tree)."""
    feats = expense_features(df, budgets)
    tree = train_tree(feats)
    if feats.empty:
        return feats, tree
    m = feats[feats["month"] == month].copy()
    preds = [tree.predict({a: r[a] for a in NECESSITY_ATTRIBUTES}) for _, r in m.iterrows()]
    m["prediction"] = [p[0] for p in preds]
    m["reason"] = [explain(p[1]) for p in preds]
    return m, tree
