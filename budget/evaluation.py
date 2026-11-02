"""Evaluate all six models on realistic data. Used by scripts/evaluate_models.py.

  k-NN    accuracy on transaction descriptions written the way they really arrive
          (bank SMS, statement PDFs, UPI apps, typed by hand), split into
            known_formats  merchants the built-in data is meant to cover
            held_out       merchants never added to the training data (generalisation)
  ID3     5-fold cross-validated accuracy on the expert examples (unseen combinations)
  LWR     walk-forward back-test error vs "same as last month" and "3-month average"
  k-Means how cleanly the planted one-off purchases are separated into their own cluster
  EM      how many planted big one-offs are flagged as unusual, and how many false alarms
  GA      whether the savings plan reaches its target without touching fixed commitments
"""

import random
from datetime import date

import numpy as np
import pandas as pd

from . import anomalies, categorizer, forecaster, necessity, patterns, planner, sample_data
from .categorizer import KNNCategorizer
from .ml.id3 import ID3DecisionTree
from .training_data import NECESSITY_ATTRIBUTES, expert_necessity_examples

# (description as it appears, type, expected category)
KNOWN_FORMATS = [
    # groceries
    ("BLINKIT", "expense", "Groceries"), ("ZEPTO", "expense", "Groceries"), ("BIGBASKET", "expense", "Groceries"),
    ("DMART READY", "expense", "Groceries"), ("JIOMART", "expense", "Groceries"),
    ("SWIGGY INSTAMART", "expense", "Groceries"), ("COUNTRY DELIGHT", "expense", "Groceries"),
    ("STAR BAZAAR", "expense", "Groceries"), ("MORE RETAIL", "expense", "Groceries"),
    ("Paid to Kirana Store", "expense", "Groceries"),
    # dining out
    ("SWIGGY", "expense", "Dining Out"), ("ZOMATO", "expense", "Dining Out"), ("DOMINOS PIZZA", "expense", "Dining Out"),
    ("MCDONALDS INDIA", "expense", "Dining Out"), ("STARBUCKS", "expense", "Dining Out"),
    ("CHAAYOS", "expense", "Dining Out"), ("BURGER KING", "expense", "Dining Out"),
    ("THIRD WAVE COFFEE", "expense", "Dining Out"), ("BEHROUZ BIRYANI", "expense", "Dining Out"),
    ("FAASOS", "expense", "Dining Out"),
    # transport
    ("UBER INDIA", "expense", "Transport"), ("OLA CABS", "expense", "Transport"), ("RAPIDO BIKE", "expense", "Transport"),
    ("HP PETROL PUMP", "expense", "Transport"), ("INDIAN OIL", "expense", "Transport"),
    ("BPCL FUEL STATION", "expense", "Transport"), ("NAMMA METRO", "expense", "Transport"),
    ("FASTAG RECHARGE", "expense", "Transport"), ("BLUSMART", "expense", "Transport"),
    # shopping
    ("AMAZON PAY INDIA", "expense", "Shopping"), ("FLIPKART", "expense", "Shopping"), ("MYNTRA", "expense", "Shopping"),
    ("AJIO", "expense", "Shopping"), ("MEESHO", "expense", "Shopping"), ("NYKAA", "expense", "Shopping"),
    ("CROMA", "expense", "Shopping"), ("TATA CLIQ", "expense", "Shopping"), ("DECATHLON", "expense", "Shopping"),
    ("LENSKART", "expense", "Shopping"),
    # utilities
    ("BESCOM ELECTRICITY", "expense", "Utilities"), ("JIO PREPAID", "expense", "Utilities"),
    ("AIRTEL POSTPAID", "expense", "Utilities"), ("ACT FIBERNET", "expense", "Utilities"),
    ("TATA PLAY DTH", "expense", "Utilities"), ("BWSSB WATER BILL", "expense", "Utilities"),
    ("INDANE GAS", "expense", "Utilities"), ("MAHANAGAR GAS", "expense", "Utilities"),
    ("VI PREPAID RECHARGE", "expense", "Utilities"),
    # healthcare
    ("APOLLO PHARMACY", "expense", "Healthcare"), ("PHARMEASY", "expense", "Healthcare"),
    ("TATA 1MG", "expense", "Healthcare"), ("MEDPLUS", "expense", "Healthcare"), ("PRACTO", "expense", "Healthcare"),
    ("MANIPAL HOSPITAL", "expense", "Healthcare"), ("DR LAL PATHLABS", "expense", "Healthcare"),
    ("THYROCARE", "expense", "Healthcare"),
    # entertainment
    ("BOOKMYSHOW", "expense", "Entertainment"), ("PVR CINEMAS", "expense", "Entertainment"),
    ("INOX MOVIES", "expense", "Entertainment"), ("WONDERLA", "expense", "Entertainment"),
    ("TIMEZONE GAMING", "expense", "Entertainment"),
    # subscriptions
    ("NETFLIX", "expense", "Subscriptions"), ("SPOTIFY INDIA", "expense", "Subscriptions"),
    ("YOUTUBE PREMIUM", "expense", "Subscriptions"), ("DISNEY HOTSTAR", "expense", "Subscriptions"),
    ("CULT FIT", "expense", "Subscriptions"), ("AMAZON PRIME", "expense", "Subscriptions"),
    ("APPLE SERVICES", "expense", "Subscriptions"), ("JIOCINEMA PREMIUM", "expense", "Subscriptions"),
    # travel
    ("MAKEMYTRIP", "expense", "Travel"), ("IRCTC", "expense", "Travel"), ("INDIGO AIRLINES", "expense", "Travel"),
    ("GOIBIBO", "expense", "Travel"), ("OYO ROOMS", "expense", "Travel"), ("REDBUS", "expense", "Travel"),
    ("AIR INDIA", "expense", "Travel"), ("YATRA ONLINE", "expense", "Travel"),
    # education
    ("BYJUS", "expense", "Education"), ("UNACADEMY", "expense", "Education"), ("UDEMY", "expense", "Education"),
    ("VEDANTU", "expense", "Education"), ("PHYSICSWALLAH", "expense", "Education"),
    ("SCHOOL FEES", "expense", "Education"),
    # insurance
    ("LIC OF INDIA", "expense", "Insurance"), ("STAR HEALTH", "expense", "Insurance"),
    ("HDFC ERGO", "expense", "Insurance"), ("ICICI LOMBARD", "expense", "Insurance"),
    ("POLICYBAZAAR", "expense", "Insurance"), ("ACKO GENERAL INSURANCE", "expense", "Insurance"),
    # loans
    ("BAJAJ FINANCE EMI", "expense", "Loan EMI"), ("HDFC LTD HOME LOAN EMI", "expense", "Loan EMI"),
    ("CREDIT CARD PAYMENT", "expense", "Loan EMI"), ("CRED CLUB", "expense", "Loan EMI"),
    ("TATA CAPITAL EMI", "expense", "Loan EMI"),
    # personal care
    ("LAKME SALON", "expense", "Personal Care"), ("URBAN COMPANY SALON", "expense", "Personal Care"),
    ("NATURALS SALON", "expense", "Personal Care"), ("GREEN TRENDS", "expense", "Personal Care"),
    # gifts & donations
    ("TEMPLE DONATION", "expense", "Gifts & Donations"), ("GIVEINDIA", "expense", "Gifts & Donations"),
    ("ISKCON", "expense", "Gifts & Donations"), ("FERNS N PETALS", "expense", "Gifts & Donations"),
    # savings
    ("ZERODHA", "expense", "Savings & Investments"), ("GROWW", "expense", "Savings & Investments"),
    ("SIP HDFC MUTUAL FUND", "expense", "Savings & Investments"),
    ("NPS CONTRIBUTION", "expense", "Savings & Investments"), ("PPF DEPOSIT", "expense", "Savings & Investments"),
    # housing
    ("NOBROKER RENT", "expense", "Housing"), ("SOCIETY MAINTENANCE", "expense", "Housing"),
    ("MYGATE MAINTENANCE", "expense", "Housing"), ("HOUSE RENT", "expense", "Housing"),
    # other
    ("ATM CASH WITHDRAWAL", "expense", "Other"),
    # income
    ("SALARY ACME TECHNOLOGIES PVT LTD", "income", "Salary"), ("SALARY", "income", "Salary"),
    ("UPWORK ESCROW", "income", "Freelance"), ("FD INTEREST", "income", "Interest & Dividends"),
    ("INTEREST PAID TILL 30-SEP-2026", "income", "Interest & Dividends"),
    ("DIVIDEND ITC LTD", "income", "Interest & Dividends"), ("RENT RECEIVED FROM TENANT", "income", "Rental Income"),
    ("CASHBACK PAYTM", "income", "Other Income"), ("REFUND AMAZON", "income", "Other Income"),
]

# Never added to the training data: measures how well k-NN generalises to merchants it has not seen.
HELD_OUT = [
    ("LICIOUS", "expense", "Groceries"), ("NAMDHARIS FRESH", "expense", "Groceries"),
    ("BLUE TOKAI COFFEE", "expense", "Dining Out"), ("BARISTA CAFE", "expense", "Dining Out"),
    ("SHELL FUEL STATION", "expense", "Transport"), ("ZOOMCAR", "expense", "Transport"),
    ("BOAT LIFESTYLE", "expense", "Shopping"), ("FIRSTCRY", "expense", "Shopping"),
    ("TORRENT POWER", "expense", "Utilities"), ("BSNL BROADBAND", "expense", "Utilities"),
    ("MEDIBUDDY", "expense", "Healthcare"), ("ASTER HOSPITAL", "expense", "Healthcare"),
    ("EASEMYTRIP", "expense", "Travel"), ("TAJ HOTELS", "expense", "Travel"),
    ("SUPERPROF TUITION", "expense", "Education"), ("NIVA BUPA HEALTH INSURANCE", "expense", "Insurance"),
    ("KOTAK HOME LOAN EMI", "expense", "Loan EMI"), ("YLG SALON", "expense", "Personal Care"),
    ("SMAAASH GAMING", "expense", "Entertainment"), ("AUDIBLE SUBSCRIPTION", "expense", "Subscriptions"),
    ("SALARY GLOBEX CORPORATION", "income", "Salary"), ("TOPTAL PAYOUT", "income", "Freelance"),
]


def _accuracy(knn: KNNCategorizer, cases) -> tuple[float, list]:
    wrong = []
    for desc, type_, expected in cases:
        got = knn.predict(desc, type_)["category"]
        if got != expected:
            wrong.append((desc, expected, got))
    return 1 - len(wrong) / len(cases), wrong


def evaluate_knn() -> dict:
    knn = KNNCategorizer()
    known, known_wrong = _accuracy(knn, KNOWN_FORMATS)
    held, held_wrong = _accuracy(knn, HELD_OUT)
    internal = categorizer.evaluate()
    return {"training_examples": knn.n_seed, "known_formats": known, "held_out": held,
            "internal_phrasing": internal["unseen_phrasing"][5], "internal_merchant": internal["unseen_merchant"][5],
            "known_wrong": known_wrong, "held_out_wrong": held_wrong}


def evaluate_id3(folds: int = 5, seed: int = 0) -> dict:
    rows, labels = expert_necessity_examples()
    idx = list(range(len(rows)))
    random.Random(seed).shuffle(idx)
    correct = 0
    for f in range(folds):
        test = set(idx[f::folds])
        tree = ID3DecisionTree().fit([rows[i] for i in idx if i not in test],
                                     [labels[i] for i in idx if i not in test], NECESSITY_ATTRIBUTES)
        correct += sum(tree.predict(rows[i])[0] == labels[i] for i in test)
    full = ID3DecisionTree().fit(rows, labels, NECESSITY_ATTRIBUTES)
    return {"examples": len(rows), "cv_accuracy": correct / len(rows), "depth": full.depth(),
            "rules": len(full.rules())}


def demo_frame(months: int, today: date) -> pd.DataFrame:
    df = pd.DataFrame(sample_data.generate(months=months, today=today))
    df["id"] = range(1, len(df) + 1)
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.strftime("%Y-%m")
    df["necessity"] = None
    return df


def evaluate_unsupervised(months: int, today: date, goal: float = 20.0) -> dict:
    df = demo_frame(months, today)
    planted = {o[1] for o in sample_data.ONE_OFFS}
    big_planted = {o[1] for o in sample_data.ONE_OFFS if o[3] >= 9000}
    out = {"months": months, "transactions": int(len(df))}

    pr = patterns.find_patterns(df, 4)
    one_off_desc = set(df.loc[df["id"].isin(pr["one_off_ids"]), "description"]) if pr else set()
    present = planted & set(df["description"])
    out["kmeans"] = {"one_offs_planted": len(present),
                     "one_offs_isolated": len(present & one_off_desc),
                     "precision": len(present & one_off_desc) / len(one_off_desc) if one_off_desc else 0.0}

    flagged = set()
    for m in sorted(df["month"].unique()):
        res = anomalies.detect(df, m)
        if res is not None:
            flagged |= set(res["flagged"]["description"])
    big_present = big_planted & set(df["description"])
    out["em"] = {"big_one_offs": len(big_present), "caught": len(big_present & flagged),
                 "false_alarms": len(flagged - planted)}

    latest = sorted(df["month"].unique())[-2]   # last complete month, so the next one can be checked
    fc = forecaster.forecast(df, latest, goal, pr["one_off_ids"] if pr else set())
    bt = fc["backtest"]
    out["lwr"] = {"tested_months": bt["tested_months"], "lwr_mae": bt["lwr_mae"], "linear_mae": bt["linear_mae"],
                  "naive_mae": bt["naive_mae"], "mean3_mae": bt["mean3_mae"], "tau": fc["tau"],
                  "next_month_error_pct": ((fc["spending_pred"] - fc["actual"]["spending"]) / fc["actual"]["spending"]
                                           * 100) if fc["actual"] else None}

    cats = fc["categories"]
    target = max(goal, round(fc["savings_rate_pred"] + 5))
    plan = planner.optimise_plan(dict(zip(cats["category"], cats["predicted"])),
                                 dict(zip(cats["category"], cats["avg_3_months"])), fc["income_pred"], target)
    touched_fixed = set(plan["plan"]["category"]) & planner.FIXED if not plan["plan"].empty else set()
    out["ga"] = {"target_pct": target, "reached": bool(plan["reached"]), "needed": plan["needed"],
                 "saved": plan["saved"], "fixed_categories_cut": sorted(touched_fixed)}
    return out


def evaluate_lwr_families(months: int, today: date, seeds=range(101, 111)) -> dict:
    """Back-test the forecast on several different demo families (one family is too few to judge by).
    Seeds 101-110 were never used while choosing the forecast settings, so this is a clean test."""
    maes = {"lwr": [], "linear": [], "naive": [], "mean3": []}
    for seed in seeds:
        df = pd.DataFrame(sample_data.generate(months=months, seed=seed, today=today))
        df["id"] = range(1, len(df) + 1)
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.strftime("%Y-%m")
        pr = patterns.find_patterns(df, 4)
        df = df[~df["id"].isin(pr["one_off_ids"] if pr else set())]
        _, spend, income = forecaster.monthly_series(df, sorted(df["month"].unique())[-1])
        bt = forecaster.backtest(spend, income)
        for k in maes:
            maes[k].append(bt[f"{k}_mae"])
    lwr = np.array(maes["lwr"])
    return {"families": len(lwr), "months": months, **{k: float(np.mean(v)) for k, v in maes.items()},
            "wins_vs_naive": int((lwr < np.array(maes["naive"])).sum()),
            "wins_vs_mean3": int((lwr < np.array(maes["mean3"])).sum())}


def evaluate_all(today: date = date(2026, 10, 29), months: int | None = None) -> dict:
    months = months or sample_data.DEFAULT_MONTHS
    return {"knn": evaluate_knn(), "id3": evaluate_id3(), "data": evaluate_unsupervised(months, today),
            "lwr_families": evaluate_lwr_families(months, today)}


def report(r: dict) -> str:
    k, i, d = r["knn"], r["id3"], r["data"]
    lines = [
        "MODEL EVALUATION",
        "=" * 60,
        f"k-NN categorizer   training examples: {k['training_examples']}",
        f"  real-world descriptions (known merchants): {k['known_formats']:.1%}",
        f"  held-out merchants never trained on:      {k['held_out']:.1%}",
        f"  internal hold-out: new phrasing {k['internal_phrasing']:.1%} · unseen merchant {k['internal_merchant']:.1%}",
        f"ID3 decision tree  {i['examples']} expert examples · 5-fold CV accuracy {i['cv_accuracy']:.1%}"
        f" · depth {i['depth']} · {i['rules']} rules",
        f"Demo data          {d['months']} months · {d['transactions']} transactions",
        f"LWR forecast       back-test over {d['lwr']['tested_months']} months (tau={d['lwr']['tau']}):"
        f" MAE {d['lwr']['lwr_mae']:.0f} vs last-month {d['lwr']['naive_mae']:.0f}"
        f" vs 3-mo avg {d['lwr']['mean3_mae']:.0f} (plain LWR {d['lwr']['linear_mae']:.0f})"
        + (f" · next month {d['lwr']['next_month_error_pct']:+.1f}%" if d['lwr']['next_month_error_pct'] is not None
           else ""),
        f"  across {r['lwr_families']['families']} other families: MAE {r['lwr_families']['lwr']:.0f}"
        f" vs last-month {r['lwr_families']['naive']:.0f} vs 3-mo avg {r['lwr_families']['mean3']:.0f}"
        f" (plain LWR {r['lwr_families']['linear']:.0f}) · beats last-month in {r['lwr_families']['wins_vs_naive']}"
        f"/{r['lwr_families']['families']}, 3-mo avg in {r['lwr_families']['wins_vs_mean3']}/{r['lwr_families']['families']}",
        f"k-Means patterns   one-offs isolated {d['kmeans']['one_offs_isolated']}/{d['kmeans']['one_offs_planted']}"
        f" · cluster precision {d['kmeans']['precision']:.0%}",
        f"EM anomalies       big one-offs caught {d['em']['caught']}/{d['em']['big_one_offs']}"
        f" · false alarms {d['em']['false_alarms']}",
        f"Genetic algorithm  target {d['ga']['target_pct']}% reached: {d['ga']['reached']}"
        f" · fixed categories cut: {d['ga']['fixed_categories_cut'] or 'none'}",
    ]
    if k["known_wrong"]:
        lines.append("  k-NN misses (known): " + "; ".join(f"{a} -> {g} (want {e})" for a, e, g in k["known_wrong"][:12]))
    if k["held_out_wrong"]:
        lines.append("  k-NN misses (held-out): " + "; ".join(f"{a} -> {g} (want {e})"
                                                             for a, e, g in k["held_out_wrong"][:12]))
    return "\n".join(lines)
