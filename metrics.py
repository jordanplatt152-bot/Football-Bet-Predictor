from __future__ import annotations

import numpy as np
import pandas as pd


def _grade(row: pd.Series) -> str:
    if row["model_status"].upper() != "ACTIVE" or row["data_quality"].upper() not in {"GOOD", "EXCELLENT"}:
        return "PASS"
    edge = row["edge"]
    prob = row["production_probability"]
    if edge >= .07 and prob >= .70:
        return "A"
    if edge >= .05 and prob >= .62:
        return "B"
    if edge >= .03 and prob >= .55:
        return "C"
    return "PASS"


def enrich_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    valid_odds = data["bookmaker_odds"] > 1
    data["market_probability"] = np.where(valid_odds, 1 / data["bookmaker_odds"], np.nan)
    data["edge"] = data["production_probability"] - data["market_probability"]
    data["expected_value"] = data["production_probability"] * data["bookmaker_odds"] - 1
    data["fair_odds"] = 1 / data["production_probability"]
    data["grade"] = data.apply(_grade, axis=1)
    data["risk"] = np.select(
        [data["grade"].eq("A"), data["grade"].eq("B"), data["grade"].eq("C")],
        ["Low", "Medium", "High"], default="Avoid",
    )
    data["fixture"] = data["home_team"] + " v " + data["away_team"]
    return data
