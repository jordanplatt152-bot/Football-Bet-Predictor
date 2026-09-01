import pandas as pd

from dashboard.metrics import enrich_predictions


def test_a_grade_requires_probability_and_edge():
    row = pd.DataFrame([{
        "match_id": "1", "home_team": "A", "away_team": "B",
        "production_probability": .72, "base_probability": .70,
        "bookmaker_odds": 1.60, "data_quality": "EXCELLENT", "model_status": "ACTIVE",
    }])
    assert enrich_predictions(row).iloc[0].grade == "A"


def test_check_status_forces_pass():
    row = pd.DataFrame([{
        "match_id": "1", "home_team": "A", "away_team": "B",
        "production_probability": .80, "base_probability": .80,
        "bookmaker_odds": 1.60, "data_quality": "EXCELLENT", "model_status": "CHECK",
    }])
    assert enrich_predictions(row).iloc[0].grade == "PASS"
