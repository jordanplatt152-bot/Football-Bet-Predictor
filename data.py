from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


REQUIRED = {
    "match_id", "date", "competition", "home_team", "away_team", "market",
    "base_probability", "production_probability", "bookmaker_odds",
    "data_quality", "model_status",
}


def _normalise_headers(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [
        str(c).strip().lower().replace("/", "_").replace(" ", "_").replace("%", "pct")
        for c in frame.columns
    ]
    aliases = {
        "match_id_": "match_id", "prod_probability": "production_probability",
        "prod_pct": "production_probability", "base_pct": "base_probability",
        "best_odds": "bookmaker_odds", "league": "competition",
    }
    return frame.rename(columns={k: v for k, v in aliases.items() if k in frame.columns})


def _validate(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(REQUIRED - set(frame.columns))
    if missing:
        raise ValueError("missing required columns: " + ", ".join(missing))
    # One fixture legitimately has several market rows. Only an identical
    # Match ID + market pair is a duplicate on this production surface.
    if frame.assign(match_id=frame["match_id"].astype(str)).duplicated(["match_id", "market"]).any():
        raise ValueError("duplicate Match ID + market rows detected")
    for col in ("base_probability", "production_probability"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame.loc[frame[col] > 1, col] /= 100
        if frame[col].isna().any() or (~frame[col].between(0, 1)).any():
            raise ValueError(f"invalid probabilities in {col}")
    frame["bookmaker_odds"] = pd.to_numeric(frame["bookmaker_odds"], errors="coerce")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if frame["date"].isna().any():
        raise ValueError("invalid fixture dates detected")
    return frame


def load_predictions() -> tuple[pd.DataFrame, str]:
    """Load a CSV adapter; fall back to clearly-labelled demonstration rows."""
    csv_url = os.getenv("PREDICTIONS_CSV_URL", "").strip()
    csv_path = os.getenv("PREDICTIONS_CSV_PATH", "").strip()
    if csv_url:
        frame = pd.read_csv(csv_url)
        note = "Live adapter: PREDICTIONS_CSV_URL"
    elif csv_path:
        frame = pd.read_csv(csv_path)
        note = f"File adapter: {csv_path}"
    else:
        demo = Path(__file__).resolve().parents[1] / "data" / "demo_predictions.csv"
        frame = pd.read_csv(demo)
        note = "DEMONSTRATION DATA — no live bets or current fixtures"
    return _validate(_normalise_headers(frame)), note
