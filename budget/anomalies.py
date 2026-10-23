"""Detect unusual / excessive expenses with a Gaussian Mixture Model trained by EM.

Each expense is a point (log amount, log(amount / usual amount in its category)).
EM learns what "normal" spending looks like for this family as a mix of K
Gaussians. An expense whose likelihood under that model is in the lowest few
percent - and that is well above the category's usual amount - is flagged.
"""

import numpy as np
import pandas as pd

from . import analyzer
from .ml.gmm_em import GaussianMixtureEM

MIN_TRANSACTIONS = 20


def detect(df: pd.DataFrame, month: str, k: int = 3, percentile: float = 4.0, min_ratio: float = 1.8) -> dict | None:
    exp = df[(df["type"] == "expense") & (df["category"] != analyzer.SAVINGS_CATEGORY)].copy()
    if len(exp) < MIN_TRANSACTIONS:
        return None
    exp["ratio"] = exp["amount"] / exp.groupby("category")["amount"].transform("median")
    raw = np.column_stack([np.log1p(exp["amount"]), np.log(exp["ratio"])])
    mean, std = raw.mean(axis=0), raw.std(axis=0)
    X = (raw - mean) / np.where(std == 0, 1, std)

    model = GaussianMixtureEM(k=k).fit(X)
    exp["log_likelihood"] = model.score_samples(X)
    exp["component"] = model.predict(X)
    threshold = float(np.percentile(exp["log_likelihood"], percentile))

    flagged = exp[(exp["month"] == month) & (exp["log_likelihood"] < threshold) & (exp["ratio"] >= min_ratio)]
    return {
        "flagged": flagged.sort_values("log_likelihood")[
            ["id", "date", "description", "category", "amount", "ratio", "log_likelihood"]],
        "all": exp,
        "threshold": threshold,
        "log_likelihood_history": model.log_likelihood_history,
        "iterations": len(model.log_likelihood_history),
    }
