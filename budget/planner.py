"""Find the best savings plan with a Genetic Algorithm.

Chromosome: one gene per category = the fraction to cut (0 .. max cut).
  - fixed commitments (rent, EMI, insurance, school, health) are never cut
  - other needs (groceries, utilities, transport) can be cut up to 10%
  - wants can be cut up to 50%
Fitness (higher is better) = -( 100 x shortfall from the savings target
                               + "pain" of the cuts
                               +   2 x overshoot beyond the target )
Pain grows with the square of each cut (a 40% cut hurts 4x a 20% cut) and is
4x higher for needs. Categories that have grown above their usual level get
lower pain, so the plan trims recent overspending first - that is what makes
the plan personal to each family.
"""

import numpy as np
import pandas as pd

from .categorizer import EXPENSE_CATEGORIES
from .ml.genetic import genetic_optimize

FIXED = {"Housing", "Loan EMI", "Insurance", "Education", "Healthcare", "Savings & Investments"}
MAX_CUT = {"need": 0.10, "want": 0.50}
PAIN = {"need": 4.0, "want": 1.0}


def optimise_plan(spend: dict[str, float], usual: dict[str, float], income: float, goal_pct: float,
                  seed: int = 0) -> dict:
    """spend: expected spending per category; usual: the family's normal level per category."""
    total = sum(spend.values())
    needed = max(0.0, goal_pct / 100 * income - (income - total))
    cats = [c for c, v in spend.items() if v > 0 and c not in FIXED and c in EXPENSE_CATEGORIES]
    result = {"needed": needed, "income": income, "spending": total, "history": [],
              "plan": pd.DataFrame(columns=["category", "type", "current", "cut_pct", "saving", "new_budget"])}
    if needed <= 0 or not cats or income <= 0:
        result.update(saved=0.0, reached=True, max_possible=0.0,
                      new_savings_rate=(income - total) / income * 100 if income else 0.0)
        return result

    s = np.array([spend[c] for c in cats])
    types = [EXPENSE_CATEGORIES[c] for c in cats]
    upper = np.array([MAX_CUT[t] for t in types])
    growth = np.array([usual.get(c, spend[c]) / spend[c] for c in cats])  # < 1 when spending grew
    pain_w = np.array([PAIN[t] for t in types]) * np.clip(growth, 0.25, 1.5)

    def fitness(pop):
        saved = pop @ s
        shortfall = np.maximum(0, needed - saved) / income
        overshoot = np.maximum(0, saved - needed) / income
        pain = (pop ** 2 * s * pain_w).sum(axis=1) / income
        return -(100 * shortfall + pain + 2 * overshoot)

    best, _, history = genetic_optimize(fitness, np.zeros(len(cats)), upper, seed=seed)
    best = np.where(best < 0.005, 0.0, best)  # drop negligible cuts
    savings = best * s
    plan = pd.DataFrame({
        "category": cats, "type": types, "current": s, "cut_pct": best * 100,
        "saving": savings, "new_budget": s - savings,
    })
    plan = plan[plan["saving"] > 0].sort_values("saving", ascending=False).reset_index(drop=True)
    saved = float(savings.sum())
    result.update(plan=plan, saved=saved, reached=saved >= needed * 0.98, max_possible=float(upper @ s),
                  history=history, new_savings_rate=(income - total + saved) / income * 100)
    return result
