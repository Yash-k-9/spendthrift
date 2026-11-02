"""Quality floors for the trained models, so changes to the training data can't quietly make them worse.

Run with:  python -m pytest -q
"""

from datetime import date

import pytest

from budget import evaluation
from budget.training_data import CATEGORY_PHRASES


@pytest.fixture(scope="module")
def knn_report():
    return evaluation.evaluate_knn()


def test_knn_handles_real_world_descriptions(knn_report):
    assert knn_report["known_formats"] >= 0.97, knn_report["known_wrong"]


def test_knn_generalises_to_unseen_merchants(knn_report):
    assert knn_report["held_out"] >= 0.75, knn_report["held_out_wrong"]
    assert knn_report["internal_merchant"] >= 0.40


def test_held_out_merchants_are_not_in_training_data():
    phrases = {p for values in CATEGORY_PHRASES.values() for p in values}
    for desc, _, _ in evaluation.HELD_OUT:
        assert desc.lower() not in phrases
        assert desc.split()[0].lower() not in {w for p in phrases for w in p.split()} or desc.startswith("SALARY")


def test_id3_generalises_to_unseen_combinations():
    r = evaluation.evaluate_id3()
    assert r["examples"] == 96 and r["cv_accuracy"] >= 0.8


def test_unsupervised_models_on_a_year_of_data():
    r = evaluation.evaluate_unsupervised(12, date(2026, 10, 29))
    assert r["kmeans"]["one_offs_isolated"] == r["kmeans"]["one_offs_planted"]
    assert r["em"]["caught"] >= 4 and r["em"]["false_alarms"] <= 1
    assert r["lwr"]["tested_months"] >= 6 and abs(r["lwr"]["next_month_error_pct"]) < 15
    assert r["ga"]["reached"] and not r["ga"]["fixed_categories_cut"]


def test_forecast_beats_plain_lwr_and_last_month_on_unseen_families():
    r = evaluation.evaluate_lwr_families(12, date(2026, 10, 29), seeds=range(101, 106))
    assert r["lwr"] < r["linear"]          # shrinking the trend helps
    assert r["lwr"] < r["naive"]           # and beats "same as last month"
    assert r["lwr"] <= r["mean3"] * 1.03   # and is at least level with the 3-month average
