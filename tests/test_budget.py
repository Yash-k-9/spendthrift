"""Tests for the from-scratch ML algorithms and the budget features built on them.

Run with:  python -m pytest -q
"""

from datetime import date

import numpy as np
import pytest

from budget import analyzer, anomalies, forecaster, necessity, patterns, planner, sample_data
from budget.categorizer import KNNCategorizer
from budget.ml.genetic import genetic_optimize
from budget.ml.gmm_em import GaussianMixtureEM
from budget.ml.id3 import ID3DecisionTree, entropy
from budget.ml.kmeans import kmeans
from budget.ml.knn import KNNClassifier
from budget.ml.lwr import lwr_predict
from budget.ml.text import TfidfVectorizer
from budget.storage import BudgetStore


@pytest.fixture(scope="module")
def knn():
    return KNNCategorizer()


@pytest.fixture
def store(tmp_path):
    s = BudgetStore(tmp_path / "test.db")
    s.add_many(sample_data.generate(today=date(2026, 10, 23)))
    return s


# ---------------------------------------------------------------- algorithms
def test_knn_votes_by_nearest_neighbours():
    vec = TfidfVectorizer()
    X = vec.fit_transform(["zomato dinner", "swiggy order", "electricity bill", "water bill"])
    model = KNNClassifier(k=1).fit(X, ["Dining", "Dining", "Utilities", "Utilities"])
    assert model.predict_one(vec.transform(["zomato lunch"])[0])[0] == "Dining"
    assert model.predict_one(vec.transform(["water"])[0])[0] == "Utilities"


def test_lwr_recovers_a_straight_line():
    assert lwr_predict([0, 1, 2, 3], [1, 3, 5, 7], 4, tau=1.0) == pytest.approx(9.0)


def test_lwr_small_tau_follows_recent_points():
    # Flat then rising: a local fit (small tau) extrapolates the recent rise more than a global one.
    x, y = [0, 1, 2, 3, 4, 5], [10, 10, 10, 10, 20, 30]
    assert lwr_predict(x, y, 6, tau=1.0) > lwr_predict(x, y, 6, tau=100.0)


def test_id3_entropy_and_learning():
    assert entropy({"yes": 5, "no": 5}) == pytest.approx(1.0)
    assert entropy({"yes": 4}) == 0.0
    rows = [{"outlook": o, "wind": w} for o in ["sunny", "rain"] for w in ["weak", "strong"]]
    labels = ["yes" if r["wind"] == "weak" else "no" for r in rows]
    tree = ID3DecisionTree().fit(rows, labels, ["outlook", "wind"])
    assert tree.tree["attribute"] == "wind"   # the only informative attribute is chosen at the root
    assert tree.predict({"outlook": "rain", "wind": "strong"}) == ("no", [("wind", "strong")])


def test_kmeans_separates_blobs():
    rng = np.random.default_rng(1)
    X = np.vstack([rng.normal(0, 0.3, (40, 2)), rng.normal(5, 0.3, (40, 2))])
    centroids, labels, _, _ = kmeans(X, 2)
    assert sorted(np.round(centroids[:, 0])) == [0, 5]
    assert len(set(labels[:40])) == 1 and len(set(labels[40:])) == 1


def test_em_finds_mixture_components_and_scores_outliers_low():
    rng = np.random.default_rng(2)
    X = np.vstack([rng.normal(0, 1, (100, 2)), rng.normal(8, 1, (100, 2))])
    model = GaussianMixtureEM(k=2).fit(X)
    assert sorted(np.round(model.means[:, 0])) == [0, 8]
    ll = model.log_likelihood_history
    assert all(b >= a - 1e-6 for a, b in zip(ll, ll[1:]))  # EM never decreases the likelihood
    assert model.score_samples(np.array([[30.0, 30.0]]))[0] < model.score_samples(np.array([[0.0, 0.0]]))[0]


def test_genetic_algorithm_minimises_quadratic():
    best, _, history = genetic_optimize(lambda P: -((P - 0.3) ** 2).sum(axis=1), [0] * 3, [1] * 3)
    assert np.allclose(best, 0.3, atol=0.02)
    assert history[-1] >= history[0]


# ---------------------------------------------------------------- budget features
@pytest.mark.parametrize("desc,type_,expected", [
    ("Swiggy order", "expense", "Dining Out"),
    ("UPI/ZOMATO/88123", "expense", "Dining Out"),
    ("BESCOM electricity", "expense", "Utilities"),
    ("Metro card recharge", "expense", "Transport"),
    ("LIC premium", "expense", "Insurance"),
    ("Spotify premium", "expense", "Subscriptions"),
    ("Croma headphones", "expense", "Shopping"),
    ("Salary credit", "income", "Salary"),
    ("Rent received from tenant", "income", "Rental Income"),
    ("random thing xyz", "expense", "Other"),
])
def test_knn_categorizer(knn, desc, type_, expected):
    assert knn.predict(desc, type_)["category"] == expected


def test_knn_flags_weak_matches_for_review(knn):
    assert knn.predict("qwerty zxcv")["needs_review"]          # only shares "rty" with "party"
    assert not knn.predict("Swiggy order")["needs_review"]


def test_knn_learns_from_corrections():
    before = KNNCategorizer().predict("Sharma uncle tuition", "expense")["category"]
    after = KNNCategorizer([("Sharma uncle tuition", "expense", "Education")]).predict("Sharma uncle tuition")
    assert before != "Education" or after["category"] == "Education"
    assert after["category"] == "Education" and after["confidence"] > 0.5


def test_kmeans_finds_one_off_purchases(store):
    result = patterns.find_patterns(store.transactions())
    one_offs = store.transactions().set_index("id").loc[list(result["one_off_ids"]), "description"]
    assert "Laptop purchase Croma" in set(one_offs)
    assert "House rent" not in set(one_offs)


def test_forecast_is_close_to_what_happened(store):
    df = store.transactions()
    one_offs = patterns.find_patterns(df)["one_off_ids"]
    fc = forecaster.forecast(df, "2026-09", 20, one_offs)
    assert fc["next_month"] == "2026-10"
    assert abs(fc["spending_pred"] - fc["actual"]["spending"]) / fc["actual"]["spending"] < 0.15
    assert 0 <= fc["prob_goal"] <= 1


def test_decision_tree_flags_frequent_wants(store):
    m, tree = necessity.classify_month(store.transactions(), "2026-10", {})
    swiggy = m[m["description"] == "Swiggy order"]
    rent = m[m["description"] == "House rent"]
    assert (swiggy["prediction"] == "Unnecessary").all()
    assert (rent["prediction"] == "Reasonable").all()


def test_decision_tree_learns_family_labels(store):
    df = store.transactions()
    petrol_ids = df.loc[df["description"] == "Petrol", "id"]
    for i in petrol_ids:
        store.set_necessity(int(i), "Unnecessary")
    m, _ = necessity.classify_month(store.transactions(), "2026-10", {})
    assert (m.loc[m["description"] == "Petrol", "prediction"] == "Unnecessary").all()


def test_em_flags_the_laptop(store):
    result = anomalies.detect(store.transactions(), "2026-10")
    assert "Laptop purchase Croma" in set(result["flagged"]["description"])
    assert "House rent" not in set(result["flagged"]["description"])


def test_ga_plan_reaches_target_without_touching_fixed_costs():
    spend = {"Housing": 18000, "Loan EMI": 7500, "Groceries": 15000, "Dining Out": 12000, "Shopping": 10000}
    plan = planner.optimise_plan(spend, usual={"Dining Out": 8000, "Shopping": 10000}, income=80000, goal_pct=30)
    assert plan["reached"]
    assert abs(plan["saved"] - plan["needed"]) / plan["needed"] < 0.05
    cuts = dict(zip(plan["plan"]["category"], plan["plan"]["cut_pct"]))
    assert "Housing" not in cuts and "Loan EMI" not in cuts
    assert cuts.get("Groceries", 0) <= 10.01
    assert cuts["Dining Out"] > cuts["Shopping"]  # Dining Out grew above usual, so it is cut first


def test_monthly_summary_math(store):
    s = analyzer.monthly_summary(store.transactions(), "2026-09")
    assert s["net_savings"] == pytest.approx(s["income"] - s["spending"])
