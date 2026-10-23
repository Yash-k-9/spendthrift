"""Spending statistics: monthly summaries, trends, rule-based alerts and tips.

Plain pandas statistics. The ML models (forecaster, necessity, patterns,
anomalies, planner) build on top of these numbers.

Terminology:
  spending      = expenses excluding "Savings & Investments"
  invested      = money moved into "Savings & Investments"
  net_savings   = income - spending   (invested money counts as saved)
  savings_rate  = net_savings / income
"""

import pandas as pd

from .categorizer import EXPENSE_CATEGORIES

SAVINGS_CATEGORY = "Savings & Investments"

# Rough healthy ceilings as a share of monthly household income.
CATEGORY_BENCHMARKS = {
    "Housing": 0.30, "Groceries": 0.15, "Utilities": 0.08, "Transport": 0.10,
    "Dining Out": 0.05, "Shopping": 0.08, "Entertainment": 0.04, "Subscriptions": 0.02,
    "Travel": 0.06, "Personal Care": 0.03, "Gifts & Donations": 0.03, "Other": 0.05,
}
# 50/30/20 rule targets.
RULE_503020 = {"need": 0.50, "want": 0.30, "saving": 0.20}


def months(df: pd.DataFrame) -> list[str]:
    return sorted(df["month"].unique(), reverse=True) if not df.empty else []


def _month(df: pd.DataFrame, month: str) -> pd.DataFrame:
    return df[df["month"] == month]


def _spend(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["type"] == "expense") & (df["category"] != SAVINGS_CATEGORY)]


def monthly_summary(df: pd.DataFrame, month: str) -> dict:
    m = _month(df, month)
    income = m.loc[m["type"] == "income", "amount"].sum()
    spending = _spend(m)["amount"].sum()
    invested = m.loc[(m["type"] == "expense") & (m["category"] == SAVINGS_CATEGORY), "amount"].sum()
    net = income - spending
    return {
        "month": month,
        "income": round(float(income), 2),
        "spending": round(float(spending), 2),
        "invested": round(float(invested), 2),
        "net_savings": round(float(net), 2),
        "savings_rate_pct": round(float(net / income * 100), 1) if income else 0.0,
        "transaction_count": int(len(m)),
    }


def category_breakdown(df: pd.DataFrame, month: str) -> pd.DataFrame:
    m = _spend(_month(df, month))
    if m.empty:
        return pd.DataFrame(columns=["category", "amount", "count", "share_pct"])
    out = m.groupby("category")["amount"].agg(amount="sum", count="count").reset_index()
    out["share_pct"] = (out["amount"] / out["amount"].sum() * 100).round(1)
    return out.sort_values("amount", ascending=False).reset_index(drop=True)


def _spend_by_category(df: pd.DataFrame, month: str) -> dict[str, float]:
    b = category_breakdown(df, month)
    return {cat: float(amt) for cat, amt in zip(b["category"], b["amount"])}


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    rows = [monthly_summary(df, m) for m in sorted(months(df))]
    return pd.DataFrame(rows)


def category_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot: rows = month, columns = category, values = spend."""
    s = _spend(df)
    if s.empty:
        return pd.DataFrame()
    return s.pivot_table(index="month", columns="category", values="amount", aggfunc="sum", fill_value=0).sort_index()


def needs_wants_split(df: pd.DataFrame, month: str) -> dict:
    m = _month(df, month)
    income = m.loc[m["type"] == "income", "amount"].sum()
    exp = m[m["type"] == "expense"]
    buckets = exp.assign(bucket=exp["category"].map(EXPENSE_CATEGORIES).fillna("want"))
    totals = buckets.groupby("bucket")["amount"].sum().to_dict()
    need, want = totals.get("need", 0.0), totals.get("want", 0.0)
    saving = max(income - need - want, 0.0)
    result = {"income": float(income)}
    for name, value in (("need", need), ("want", want), ("saving", saving)):
        result[name] = round(float(value), 2)
        result[f"{name}_pct"] = round(float(value / income * 100), 1) if income else 0.0
        result[f"{name}_target_pct"] = RULE_503020[name] * 100
    return result


def _previous_months(df: pd.DataFrame, month: str, n: int = 3) -> list[str]:
    return [m for m in sorted(months(df)) if m < month][-n:]


def category_baseline(df: pd.DataFrame, month: str, n: int = 3) -> dict[str, float]:
    """Average monthly spend per category over the n months before `month`."""
    prev = _previous_months(df, month, n)
    if not prev:
        return {}
    s = _spend(df[df["month"].isin(prev)])
    return (s.groupby("category")["amount"].sum() / len(prev)).round(2).to_dict()


def detect_issues(df: pd.DataFrame, month: str, budgets: dict[str, float], savings_goal_pct: float) -> list[dict]:
    """Find unnecessary, excessive or unusual spending in a month.

    Each issue: {severity: high|medium|low, kind, category, title, detail, excess}
    `excess` is the estimated avoidable amount, used to rank issues.
    """
    issues = []
    summary = monthly_summary(df, month)
    income = summary["income"]
    spend_by_cat = _spend_by_category(df, month)
    baseline = category_baseline(df, month)
    m_spend = _spend(_month(df, month))

    # 1. Savings goal missed
    if income and summary["savings_rate_pct"] < savings_goal_pct:
        gap = income * savings_goal_pct / 100 - summary["net_savings"]
        issues.append({
            "severity": "high" if summary["savings_rate_pct"] < savings_goal_pct / 2 else "medium",
            "kind": "savings_goal", "category": None,
            "title": f"Savings rate {summary['savings_rate_pct']}% is below the {savings_goal_pct:g}% goal",
            "detail": f"Need to save {gap:,.0f} more this month to hit the goal.",
            "excess": round(gap, 2),
        })

    # 2. Over the family's own category budgets
    for cat, limit in budgets.items():
        spent = spend_by_cat.get(cat, 0.0)
        if limit > 0 and spent > limit:
            over = spent - limit
            issues.append({
                "severity": "high" if over > 0.25 * limit else "medium",
                "kind": "over_budget", "category": cat,
                "title": f"{cat} is over budget by {over:,.0f}",
                "detail": f"Spent {spent:,.0f} against a limit of {limit:,.0f} ({spent / limit * 100:.0f}%).",
                "excess": round(over, 2),
            })

    # 3. Above healthy share of income (benchmarks)
    if income:
        for cat, spent in spend_by_cat.items():
            ceiling = CATEGORY_BENCHMARKS.get(cat)
            if ceiling and spent > ceiling * income and cat not in budgets:
                over = spent - ceiling * income
                issues.append({
                    "severity": "medium" if EXPENSE_CATEGORIES.get(cat) == "want" else "low",
                    "kind": "above_benchmark", "category": cat,
                    "title": f"{cat} takes {spent / income * 100:.1f}% of income",
                    "detail": f"A healthy ceiling is about {ceiling * 100:.0f}% ({ceiling * income:,.0f}).",
                    "excess": round(over, 2),
                })

    # 4. Spikes vs. the family's own recent average
    for cat, spent in spend_by_cat.items():
        avg = baseline.get(cat, 0.0)
        if avg > 0 and spent > 1.4 * avg and spent - avg > max(0.02 * income, 500):
            issues.append({
                "severity": "medium",
                "kind": "spike", "category": cat,
                "title": f"{cat} spending jumped {(spent / avg - 1) * 100:.0f}%",
                "detail": f"{spent:,.0f} this month vs. a 3-month average of {avg:,.0f}.",
                "excess": round(spent - avg, 2),
            })

    # 5. Frequent small discretionary purchases (the "latte factor")
    for cat in ("Dining Out", "Shopping", "Entertainment"):
        rows = m_spend[m_spend["category"] == cat]
        if len(rows) >= 8:
            issues.append({
                "severity": "low",
                "kind": "frequency", "category": cat,
                "title": f"{len(rows)} separate {cat.lower()} purchases",
                "detail": f"Small frequent spends add up to {rows['amount'].sum():,.0f}. "
                          f"Halving the count would save ~{rows['amount'].sum() / 2:,.0f}.",
                "excess": round(rows["amount"].sum() / 2, 2),
            })

    # 6. Subscriptions - list them so the family can review
    subs = m_spend[m_spend["category"] == "Subscriptions"]
    if len(subs) >= 3:
        names = ", ".join(sorted(subs["description"].unique()))
        issues.append({
            "severity": "low",
            "kind": "subscriptions", "category": "Subscriptions",
            "title": f"{len(subs)} active subscriptions ({subs['amount'].sum():,.0f}/month)",
            "detail": f"Review whether all are used: {names}.",
            "excess": round(subs["amount"].min(), 2),
        })

    # (Unusually large single transactions are found by the EM model - see anomalies.py.)

    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (order[i["severity"]], -i["excess"]))
    return issues


def suggest_budgets(df: pd.DataFrame, month: str) -> dict[str, float]:
    """Suggested monthly limits: needs at their recent average, wants trimmed 15%."""
    base = category_baseline(df, month, n=3) or _spend_by_category(df, month)
    out = {}
    for cat, avg in base.items():
        factor = 0.85 if EXPENSE_CATEGORIES.get(cat) == "want" else 1.0
        out[cat] = float(round(avg * factor / 100) * 100)  # round to nearest 100
    return out


def simulate_savings(df: pd.DataFrame, month: str, cuts: dict[str, float]) -> dict:
    """What-if: cut each category by the given percent; return the new savings picture."""
    summary = monthly_summary(df, month)
    breakdown = _spend_by_category(df, month)
    saved_by_cat = {cat: round(breakdown.get(cat, 0.0) * pct / 100, 2) for cat, pct in cuts.items()}
    extra = sum(saved_by_cat.values())
    new_net = summary["net_savings"] + extra
    income = summary["income"]
    return {
        "monthly_extra_savings": round(extra, 2),
        "yearly_extra_savings": round(extra * 12, 2),
        "by_category": saved_by_cat,
        "old_savings_rate_pct": summary["savings_rate_pct"],
        "new_savings_rate_pct": round(new_net / income * 100, 1) if income else 0.0,
    }


def recommendations(df: pd.DataFrame, month: str, budgets: dict[str, float], savings_goal_pct: float) -> list[str]:
    """Plain-language, rule-based tips (used offline and as context for the AI agent)."""
    tips = []
    summary = monthly_summary(df, month)
    split = needs_wants_split(df, month)
    issues = detect_issues(df, month, budgets, savings_goal_pct)

    if split["want_pct"] > 30:
        tips.append(f"Wants are {split['want_pct']}% of income (target 30%). Bringing them to 30% "
                    f"frees up {split['want'] - 0.3 * split['income']:,.0f} a month.")
    seen = set()
    for issue in issues:
        cat = issue["category"]
        if not cat or cat in seen or issue["excess"] <= 0:
            continue
        seen.add(cat)
        if issue["kind"] in ("over_budget", "above_benchmark", "spike"):
            tips.append(f"Trim {cat}: cutting the excess saves about {issue['excess']:,.0f}/month "
                        f"({issue['excess'] * 12:,.0f}/year).")
        elif issue["kind"] == "frequency":
            tips.append(f"Plan {cat.lower()} ahead - fewer, planned purchases instead of many small ones "
                        f"could save ~{issue['excess']:,.0f}/month.")
        elif issue["kind"] == "subscriptions":
            tips.append("Cancel or share at least one subscription; family plans are usually cheaper.")
        if len(tips) >= 5:
            break
    if summary["invested"] == 0 and summary["net_savings"] > 0:
        tips.append(f"You saved {summary['net_savings']:,.0f} but invested nothing. Automate a SIP/recurring "
                    f"deposit on salary day so savings don't get spent.")
    if summary["income"] and summary["savings_rate_pct"] >= savings_goal_pct:
        tips.append(f"Great job - you met your {savings_goal_pct:g}% savings goal. Consider building a "
                    f"6-month emergency fund ({summary['spending'] * 6:,.0f}).")
    if not budgets:
        tips.append("Set monthly limits per category - families that budget per category overspend less.")
    return tips
