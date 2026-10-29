"""Spending plans, over-target alerts and the rewards game.

Plans
  The family decides, for any period (a month, a week, a trip...), what they
  expect to spend: a total ceiling plus planned amounts per category. Progress
  compares real spending in that period with the plan, and projects the end of
  the period at the current pace.

Alerts
  Raised at 80% (warning) and 100% (exceeded) of a plan's total or of a planned
  category, and when a monthly category budget is exceeded. Each alert has a
  stable id so the browser notifies about it only once.

Rewards (a game, recomputed from the data so points can't drift)
  +10  clean day: a day with no unnecessary expense (ID3 + family labels); no-spend days count too
  +30  every 7-day clean streak
  -1   per 250 spent on an unnecessary expense (min 1, max 10 per expense)
  +100 a finished plan that stayed within its total   /  -50 one that went over
  +10  each planned category that stayed within its amount
  +75  a finished month that met the savings goal
Points add up to levels and badges, and to a family-member leaderboard.
"""

import math
from datetime import date, timedelta

import pandas as pd

from . import analyzer, necessity

WARN_AT = 0.8
LEVELS = [(0, "🌱 Seedling"), (250, "🥉 Bronze Saver"), (600, "🥈 Silver Saver"), (1200, "🥇 Gold Saver"),
          (2000, "💎 Platinum Saver"), (3500, "👑 Budget Master")]
POINTS = {"clean_day": 10, "streak_7": 30, "plan_kept": 100, "plan_broken": -50, "category_kept": 10,
          "savings_goal": 75}


def _expenses(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["type"] == "expense") & (df["category"] != analyzer.SAVINGS_CATEGORY)]


def _day(d) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


# ---------------------------------------------------------------- plans
def plan_progress(df: pd.DataFrame, plan: dict, today: date | None = None) -> dict:
    today = today or date.today()
    start, end = _day(plan["start_date"]), _day(plan["end_date"])
    exp = _expenses(df)
    if not exp.empty:
        days = exp["date"].dt.date
        exp = exp[(days >= start) & (days <= end)]
    spent_by_cat = exp.groupby("category")["amount"].sum().to_dict() if not exp.empty else {}
    spent = float(sum(spent_by_cat.values()))

    total_days = (end - start).days + 1
    elapsed = min(max((today - start).days + 1, 0), total_days)
    status = "upcoming" if today < start else "finished" if today > end else "active"
    projected = spent / elapsed * total_days if status == "active" and elapsed else spent

    planned = {i["category"]: float(i["amount"]) for i in plan["items"]}
    categories = []
    for cat in dict.fromkeys(list(planned) + sorted(spent_by_cat)):
        p, s = planned.get(cat), float(spent_by_cat.get(cat, 0.0))
        categories.append({"category": cat, "planned": p, "spent": s, "pct": (s / p) if p else None,
                           "unplanned": p is None})
    target = float(plan["target_total"])
    return {**plan, "status": status, "spent": spent, "remaining": target - spent,
            "pct": spent / target if target else 0.0, "projected": projected,
            "days_total": total_days, "days_elapsed": elapsed, "days_left": max(total_days - elapsed, 0),
            "planned_total": float(sum(planned.values())), "categories": categories,
            "transactions": int(len(exp))}


# ---------------------------------------------------------------- alerts
def alerts(df: pd.DataFrame, plans: list[dict], budgets: dict[str, float], today: date | None = None,
           currency: str = "₹") -> list[dict]:
    today = today or date.today()
    out = []

    def money(x):
        return f"{currency}{x:,.0f}"

    for plan in plans:
        p = plan_progress(df, plan, today)
        if p["status"] != "active":
            continue
        for level, threshold in (("exceeded", 1.0), ("warning", WARN_AT)):
            if p["target_total"] and p["pct"] >= threshold:
                out.append({
                    "id": f"plan{p['id']}-total-{level}", "level": level, "plan_id": p["id"],
                    "title": (f"Over your plan “{p['name']}”" if level == "exceeded"
                              else f"{p['pct']:.0%} of “{p['name']}” used"),
                    "detail": f"Spent {money(p['spent'])} of {money(p['target_total'])}"
                              f" with {p['days_left']} day(s) left.",
                })
                break
        for c in p["categories"]:
            if c["planned"] is None or not c["planned"]:
                continue
            for level, threshold in (("exceeded", 1.0), ("warning", WARN_AT)):
                if c["pct"] >= threshold:
                    out.append({
                        "id": f"plan{p['id']}-{c['category']}-{level}", "level": level, "plan_id": p["id"],
                        "title": (f"{c['category']} is over plan" if level == "exceeded"
                                  else f"{c['category']} at {c['pct']:.0%} of plan"),
                        "detail": f"{money(c['spent'])} of {money(c['planned'])} planned in “{p['name']}”.",
                    })
                    break
        if p["target_total"] and p["pct"] < WARN_AT and p["projected"] > p["target_total"] * 1.05 \
                and p["days_elapsed"] >= 3:
            out.append({"id": f"plan{p['id']}-pace-{today.isoformat()}", "level": "info", "plan_id": p["id"],
                        "title": f"On pace to overspend “{p['name']}”",
                        "detail": f"At this rate you'll spend about {money(p['projected'])}"
                                  f" (plan {money(p['target_total'])})."})

    month = today.strftime("%Y-%m")
    exp = _expenses(df)
    if not exp.empty and budgets:
        spent = exp[exp["month"] == month].groupby("category")["amount"].sum()
        for cat, limit in budgets.items():
            if limit > 0 and spent.get(cat, 0.0) > limit:
                out.append({"id": f"budget-{month}-{cat}", "level": "exceeded", "plan_id": None,
                            "title": f"{cat} budget exceeded",
                            "detail": f"{money(spent[cat])} spent this month vs {money(limit)} budget."})
    order = {"exceeded": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda a: order[a["level"]])


# ---------------------------------------------------------------- rewards
def unnecessary_flags(df: pd.DataFrame, budgets: dict[str, float]) -> pd.DataFrame:
    """Every expense with unnecessary = the family's own label if set, else the ID3 prediction."""
    feats = necessity.expense_features(df, budgets)
    if feats.empty:
        return feats.assign(unnecessary=pd.Series(dtype=bool))
    tree = necessity.train_tree(feats)
    pred = [tree.predict({a: r[a] for a in necessity.NECESSITY_ATTRIBUTES})[0] for _, r in feats.iterrows()]
    label = feats["necessity"] if "necessity" in feats else pd.Series(None, index=feats.index)
    final = [lbl if isinstance(lbl, str) and lbl else p for lbl, p in zip(label, pred)]
    return feats.assign(unnecessary=[f == "Unnecessary" for f in final])


def penalty(amount: float) -> int:
    return -min(10, max(1, math.ceil(amount / 250)))


def rewards(df: pd.DataFrame, plans: list[dict], budgets: dict[str, float], savings_goal_pct: float,
            today: date | None = None) -> dict:
    today = today or date.today()
    events = []   # {date, points, kind, text, member}
    flags = unnecessary_flags(df, budgets)

    longest = current = 0
    if not flags.empty:
        for _, r in flags[flags["unnecessary"]].iterrows():
            events.append({"date": r["date"].date().isoformat(), "points": penalty(r["amount"]),
                           "kind": "unnecessary", "member": r["member"],
                           "text": f"Unnecessary: {r['description']} ({r['amount']:,.0f})"})
        by_day = flags.groupby(flags["date"].dt.date)["unnecessary"].any()
        first, last = min(by_day.index), min(max(by_day.index), today)
        streak, d = 0, first
        while d <= last:
            if not by_day.get(d, False):                  # nothing unnecessary (no-spend days count too)
                streak += 1
                events.append({"date": d.isoformat(), "points": POINTS["clean_day"], "kind": "clean_day",
                               "member": None, "text": "Clean day: no unnecessary spending"
                               if d in by_day.index else "No-spend day"})
                if streak % 7 == 0:
                    events.append({"date": d.isoformat(), "points": POINTS["streak_7"], "kind": "streak",
                                   "member": None, "text": f"🔥 {streak}-day clean streak"})
            else:                                          # an unnecessary expense breaks the streak
                streak = 0
            longest = max(longest, streak)
            d += timedelta(days=1)
        current = streak

    for plan in plans:
        p = plan_progress(df, plan, today)
        if p["status"] != "finished" or not p["transactions"]:
            continue
        kept = p["spent"] <= p["target_total"]
        events.append({"date": p["end_date"], "points": POINTS["plan_kept"] if kept else POINTS["plan_broken"],
                       "kind": "plan", "member": None,
                       "text": f"Plan “{p['name']}” {'kept 🎉' if kept else 'went over'}"})
        for c in p["categories"]:
            if c["planned"] and c["spent"] <= c["planned"]:
                events.append({"date": p["end_date"], "points": POINTS["category_kept"], "kind": "category",
                               "member": None, "text": f"{c['category']} within plan in “{p['name']}”"})

    this_month = today.strftime("%Y-%m")
    for m in sorted(analyzer.months(df)) if not df.empty else []:
        if m >= this_month:
            continue
        s = analyzer.monthly_summary(df, m)
        if s["income"] and s["savings_rate_pct"] >= savings_goal_pct:
            events.append({"date": f"{m}-28", "points": POINTS["savings_goal"], "kind": "savings", "member": None,
                           "text": f"Savings goal met in {pd.Period(m).strftime('%B %Y')} ({s['savings_rate_pct']}%)"})

    events.sort(key=lambda e: e["date"], reverse=True)
    total = sum(e["points"] for e in events)
    earned = sum(e["points"] for e in events if e["points"] > 0)
    lost = -sum(e["points"] for e in events if e["points"] < 0)

    idx = max(i for i, (lo, _) in enumerate(LEVELS) if max(total, 0) >= lo)
    level = {"name": LEVELS[idx][1], "min": LEVELS[idx][0],
             "next_name": LEVELS[idx + 1][1] if idx + 1 < len(LEVELS) else None,
             "next_min": LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None}

    month_events = [e for e in events if e["date"].startswith(this_month)]
    unnecessary_this_month = flags[(flags["unnecessary"]) & (flags["month"] == this_month)] if not flags.empty else flags
    kinds = {e["kind"] for e in events}
    badges = [
        {"name": "🔥 Week Warrior", "desc": "7 clean days in a row", "earned": longest >= 7},
        {"name": "🏅 Fortnight Focus", "desc": "14 clean days in a row", "earned": longest >= 14},
        {"name": "📋 Planner", "desc": "Create your first spending plan", "earned": bool(plans)},
        {"name": "🎯 Plan Keeper", "desc": "Finish a plan within its total",
         "earned": any(e["kind"] == "plan" and e["points"] > 0 for e in events)},
        {"name": "💰 Saver", "desc": "Meet the monthly savings goal", "earned": "savings" in kinds},
        {"name": "🧘 Mindful Month", "desc": "Fewer than 3 unnecessary expenses this month",
         "earned": not flags.empty and len(unnecessary_this_month) < 3 and today.day >= 20},
    ]

    leaderboard = []
    if not flags.empty:
        for member, g in flags.groupby("member"):
            pts = sum(penalty(a) for a in g.loc[g["unnecessary"], "amount"])
            leaderboard.append({"member": member, "unnecessary": int(g["unnecessary"].sum()),
                                "unnecessary_amount": float(g.loc[g["unnecessary"], "amount"].sum()),
                                "expenses": int(len(g)),
                                "share_unnecessary": float(g["unnecessary"].mean()),
                                "penalty_points": pts})
        leaderboard.sort(key=lambda m: (m["share_unnecessary"], m["unnecessary_amount"]))

    return {
        "total": total, "earned": earned, "lost": lost,
        "this_month": sum(e["points"] for e in month_events),
        "level": level, "streak": current, "longest_streak": longest,
        "badges": badges, "events": events[:60], "leaderboard": leaderboard,
        "rules": [
            f"+{POINTS['clean_day']} for each clean day (no unnecessary expense; no-spend days count too)",
            f"+{POINTS['streak_7']} bonus for every 7-day clean streak",
            "−1 per 250 spent on an unnecessary expense (min −1, max −10 each)",
            f"+{POINTS['plan_kept']} for finishing a plan within its total, {POINTS['plan_broken']} if it goes over",
            f"+{POINTS['category_kept']} for each planned category kept within its amount",
            f"+{POINTS['savings_goal']} for each month that meets your savings goal",
        ],
    }
