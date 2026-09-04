from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = [
    "feed_contract_version", "feed_generated_utc", "match_id", "date", "competition",
    "home_team", "away_team", "market", "home_expected_goals", "away_expected_goals", "expected_total_goals",
    "base_probability", "production_probability",
    "model_score", "model_grade", "data_quality", "model_status", "exchange_back_odds",
    "effective_exchange_odds", "bookmaker_odds", "fractional_odds", "price_source",
    "available_liquidity_gbp", "price_timestamp_utc", "event_commence_utc",
    "pre_match_cutoff_utc", "implied_probability", "probability_edge", "expected_value",
    "price_grade", "stored_decision", "feed_price_age_minutes", "feed_status",
    "feed_candidate", "rejection_reasons", "justification",
]

NUMERIC_COLUMNS = [
    "home_expected_goals", "away_expected_goals", "expected_total_goals",
    "base_probability", "production_probability", "model_score", "exchange_back_odds",
    "effective_exchange_odds", "bookmaker_odds", "available_liquidity_gbp",
    "implied_probability", "probability_edge", "expected_value", "feed_price_age_minutes",
]
TIMESTAMP_COLUMNS = [
    "feed_generated_utc", "price_timestamp_utc", "event_commence_utc", "pre_match_cutoff_utc",
]


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    if text == "TRUE":
        return True
    if text == "FALSE":
        return False
    raise ValueError("invalid feed_candidate boolean")


def validate_feed(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data.columns = [str(column).strip().lower() for column in data.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError("missing required columns: " + ", ".join(missing))
    extra = [column for column in data.columns if column not in REQUIRED_COLUMNS]
    if extra:
        raise ValueError("unexpected feed columns: " + ", ".join(extra))
    data = data[REQUIRED_COLUMNS]

    if not data["feed_contract_version"].astype(str).eq("1.2").all():
        raise ValueError("unsupported feed contract; expected 1.2")
    for column in ("match_id", "competition", "home_team", "away_team", "market"):
        data[column] = data[column].astype(str).str.strip()
        if data[column].eq("").any():
            raise ValueError(f"blank required values in {column}")
    if data.duplicated(["match_id", "market"]).any():
        raise ValueError("duplicate match_id + market rows detected")

    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.normalize()
    if data["date"].isna().any():
        raise ValueError("invalid date")
    for column in TIMESTAMP_COLUMNS:
        data[column] = pd.to_datetime(data[column], errors="coerce", utc=True)
    if data["feed_generated_utc"].isna().any():
        raise ValueError("invalid feed_generated_utc")

    for column in NUMERIC_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    for column in ("base_probability", "production_probability"):
        if data[column].isna().any() or (~data[column].between(0, 1)).any():
            raise ValueError(f"invalid {column}")
    if data["model_score"].isna().any() or (~data["model_score"].between(0, 100)).any():
        raise ValueError("invalid model_score")
    for column in ("home_expected_goals", "away_expected_goals", "expected_total_goals"):
        if data[column].isna().any() or (data[column] < 0).any():
            raise ValueError(f"invalid {column}")
    if ((data["home_expected_goals"] + data["away_expected_goals"] - data["expected_total_goals"]).abs() > 1e-9).any():
        raise ValueError("expected_total_goals must equal home_expected_goals + away_expected_goals")

    both_prices = data[["bookmaker_odds", "effective_exchange_odds"]].notna().all(axis=1)
    mismatch = both_prices & ((data["bookmaker_odds"] - data["effective_exchange_odds"]).abs() > 1e-9)
    if mismatch.any():
        raise ValueError("bookmaker_odds must equal effective_exchange_odds")
    data["feed_candidate"] = data["feed_candidate"].map(_parse_bool)
    return data


def apply_dashboard_safety(frame: pd.DataFrame, now_utc: pd.Timestamp) -> pd.DataFrame:
    data = frame.copy()
    now = pd.Timestamp(now_utc)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    data["fixture"] = data["home_team"] + " v " + data["away_team"]
    data["fair_odds"] = 1 / data["production_probability"]
    data["dashboard_price_age_minutes"] = (
        now - data["price_timestamp_utc"]
    ).dt.total_seconds() / 60

    statuses = []
    candidates = []
    reasons_out = []
    allowed_grades = {"A", "B", "C"}
    for _, row in data.iterrows():
        reasons = [x for x in str(row.get("rejection_reasons", "")).split("|") if x and x.lower() != "nan" and "LIQUIDITY" not in x.upper()]
        status = str(row["feed_status"]).strip().upper()
        candidate = bool(row["feed_candidate"]) and status == "VALUE_CANDIDATE"
        age = row["dashboard_price_age_minutes"]

        if pd.isna(row["price_timestamp_utc"]):
            status, candidate = "UNPRICED", False
            reasons.append("PRICE_TIMESTAMP_MISSING")
        elif now >= row["pre_match_cutoff_utc"] or row["price_timestamp_utc"] >= row["pre_match_cutoff_utc"]:
            status, candidate = "POST_CUTOFF", False
            reasons.append("PRE_MATCH_CUTOFF_REACHED")
        elif age < 0:
            status, candidate = "FUTURE_TIMESTAMP", False
            reasons.append("FUTURE_PRICE_TIMESTAMP")
        elif age > 10:
            status, candidate = "STALE", False
            reasons.append("STALE_PRICE")
        elif str(row["model_status"]).upper() != "ACTIVE" or str(row["data_quality"]).upper() != "PASS":
            status, candidate = "CHECK", False
            reasons.append("MODEL_OR_DATA_CONTROL")
        elif str(row["model_grade"]).upper() not in allowed_grades:
            status, candidate = "MODEL_PASS", False
            reasons.append("MODEL_STRENGTH_PASS")
        elif str(row["price_grade"]).upper() not in allowed_grades:
            status, candidate = "NO_VALUE", False
            reasons.append("PRICE_VALUE_BELOW_C")
        elif not candidate:
            # Downgrade-only: a non-candidate from the feed can never be promoted.
            reasons.append("FEED_NOT_CANDIDATE")

        statuses.append(status)
        candidates.append(candidate)
        reasons_out.append("|".join(dict.fromkeys(reasons)))

    data["dashboard_status"] = statuses
    data["dashboard_candidate"] = candidates
    data["dashboard_rejection_reasons"] = reasons_out
    return data


def select_adapter(csv_url: str, csv_path: str) -> str:
    if str(csv_url or "").strip():
        return "LIVE_URL"
    if str(csv_path or "").strip():
        return "LIVE_FILE"
    return "DEMO"


def sort_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    grade_rank = {"A": 0, "B": 1, "C": 2, "PASS": 3}
    data = frame.copy()
    data["_grade_rank"] = data["price_grade"].astype(str).str.upper().map(grade_rank).fillna(4)
    return data.sort_values(
        ["_grade_rank", "expected_value", "production_probability"],
        ascending=[True, False, False], kind="stable",
    ).drop(columns="_grade_rank")


def with_display_percentages(frame: pd.DataFrame) -> pd.DataFrame:
    """Add percentage-point display columns without changing model inputs."""
    data = frame.copy()
    data["model_percent_display"] = data["production_probability"] * 100
    data["edge_percent_display"] = data["probability_edge"] * 100
    data["ev_percent_display"] = data["expected_value"] * 100
    return data


def _age_clock(minutes) -> str:
    if pd.isna(minutes) or float(minutes) < 0:
        return "—"
    seconds = int(round(float(minutes) * 60))
    hours, rem = divmod(seconds, 3600)
    mins, secs = divmod(rem, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}"


def build_model_rationale(row: pd.Series) -> str:
    """Explain the model selection using model evidence only; never price/value inputs."""
    market = str(row.get("market", "Model selection"))
    home_xg = float(row["home_expected_goals"])
    away_xg = float(row["away_expected_goals"])
    total_xg = float(row["expected_total_goals"])
    probability = float(row["production_probability"])
    if market.startswith("BTTS"):
        return (f"Model projects Home xG {home_xg:.2f} and Away xG {away_xg:.2f} from the teams' "
                f"venue-specific scoring/conceding profile; this produces a {probability:.1%} model probability for {market}.")
    return (f"Model projects {total_xg:.2f} total goals (Home xG {home_xg:.2f}, Away xG {away_xg:.2f}) from the teams' "
            f"venue-specific scoring/conceding profile; this produces a {probability:.1%} model probability for {market}.")


def with_qol_display(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["exchange_price_display"] = data["fractional_odds"].fillna("").astype(str).str.strip().str.replace(r"^~\s*", "", regex=True)
    data["price_age_clock"] = data["dashboard_price_age_minutes"].map(_age_clock)
    data["model_rationale"] = data.apply(build_model_rationale, axis=1)
    return data


def with_fixture_kickoff_display(frame: pd.DataFrame) -> pd.DataFrame:
    """Add UK-local date and 24-hour kickoff display from event_commence_utc."""
    data = frame.copy()
    kickoff = pd.to_datetime(data["event_commence_utc"], errors="coerce", utc=True)
    uk = kickoff.dt.tz_convert("Europe/London")
    data["date_display"] = uk.dt.strftime("%a %d %b")
    data["kickoff_display"] = uk.dt.strftime("%H:%M")
    data.loc[kickoff.isna(), ["date_display", "kickoff_display"]] = "—"
    return data


def filter_dashboard_date(frame: pd.DataFrame, date_mode: str, now_utc: pd.Timestamp) -> pd.DataFrame:
    """Filter display rows by UK-local Today/Tomorrow without changing eligibility."""
    if date_mode == "All dates":
        return frame.copy()
    now = pd.Timestamp(now_utc)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    today = now.tz_convert("Europe/London").date()
    target = today if date_mode == "Today" else today + pd.Timedelta(days=1) if date_mode == "Tomorrow" else None
    if target is None:
        raise ValueError(f"unsupported dashboard date mode: {date_mode}")
    kickoff = pd.to_datetime(frame["event_commence_utc"], errors="coerce", utc=True).dt.tz_convert("Europe/London")
    return frame[kickoff.dt.date == target].copy()



def filter_live_candidates_by_bet_type(frame: pd.DataFrame, bet_type: str) -> pd.DataFrame:
    """Filter already-qualified live candidates by exact market selection for display only."""
    if bet_type == "All":
        return frame.copy()
    return frame[frame["market"].astype(str).eq(str(bet_type))].copy()

def sort_dashboard_rows(frame: pd.DataFrame, sort_mode: str) -> pd.DataFrame:
    """Sort display rows without changing eligibility or model/value calculations."""
    data = frame.copy()
    if sort_mode == "Kickoff — earliest first":
        return data.sort_values("event_commence_utc", ascending=True, kind="stable", na_position="last")
    if sort_mode == "Kickoff — latest first":
        return data.sort_values("event_commence_utc", ascending=False, kind="stable", na_position="last")
    if sort_mode == "Model/value ranking":
        return sort_candidates(data)
    raise ValueError(f"unsupported dashboard sort mode: {sort_mode}")


def fixture_summary_rows(frame: pd.DataFrame, sort_mode: str) -> list[dict]:
    """Build read-only fixture-first summaries from already prepared dashboard rows."""
    ordered = sort_dashboard_rows(frame, sort_mode)
    summaries = []
    for _, group in ordered.groupby("match_id", sort=False):
        first = group.iloc[0]
        ranked = group.sort_values(["production_probability", "model_grade"], ascending=[False, True], kind="stable")
        top = [
            (str(row.market), float(row.production_probability), str(row.model_grade))
            for _, row in ranked.head(3).iterrows()
        ]
        summaries.append({
            "match_id": first.match_id,
            "date": first.date_display,
            "kickoff": first.kickoff_display,
            "fixture": first.fixture,
            "competition": first.competition,
            "home_xg": float(first.home_expected_goals),
            "away_xg": float(first.away_expected_goals),
            "total_xg": float(first.expected_total_goals),
            "top_selections": top,
        })
    return summaries
