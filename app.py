from __future__ import annotations

import io
import os

import numpy as np
import pandas as pd
import streamlit as st


REQUIRED = {
    "match_id", "date", "competition", "home_team", "away_team", "market",
    "base_probability", "production_probability", "bookmaker_odds",
    "data_quality", "model_status",
}

DEMO_CSV = """match_id,date,competition,home_team,away_team,market,base_probability,production_probability,bookmaker_odds,data_quality,model_status,justification
DEMO-001,2026-09-05,Premier League,Northbridge FC,Riverside United,BTTS Yes,0.67,0.71,1.62,EXCELLENT,ACTIVE,Strong opposing attack profiles; demonstration only.
DEMO-001,2026-09-05,Premier League,Northbridge FC,Riverside United,Over 2.5,0.61,0.61,1.85,EXCELLENT,ACTIVE,Total-goals distribution supports the line; demonstration only.
DEMO-001,2026-09-05,Premier League,Northbridge FC,Riverside United,Home Win,0.56,0.56,2.05,GOOD,ACTIVE,Home-side advantage in the sample; demonstration only.
DEMO-002,2026-09-06,Championship,Albion Town,County Athletic,Over 1.5,0.77,0.77,1.38,GOOD,ACTIVE,High base probability but limited market edge; demonstration only.
DEMO-002,2026-09-06,Championship,Albion Town,County Athletic,Under 3.5,0.73,0.73,1.55,GOOD,ACTIVE,Score distribution concentrated below four goals; demonstration only.
DEMO-003,2026-09-06,League One,City Rovers,Wanderers FC,Away Win,0.46,0.46,2.45,MIXED,CHECK,Data-quality guard forces PASS; demonstration only.
"""


def normalise_headers(frame: pd.DataFrame) -> pd.DataFrame:
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


def validate(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(REQUIRED - set(frame.columns))
    if missing:
        raise ValueError("missing required columns: " + ", ".join(missing))
    frame["match_id"] = frame["match_id"].astype(str)
    if frame.duplicated(["match_id", "market"]).any():
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


@st.cache_data(ttl=300)
def load_predictions() -> tuple[pd.DataFrame, str]:
    csv_url = os.getenv("PREDICTIONS_CSV_URL", "").strip()
    csv_path = os.getenv("PREDICTIONS_CSV_PATH", "").strip()
    if csv_url:
        return validate(normalise_headers(pd.read_csv(csv_url))), "Live adapter: PREDICTIONS_CSV_URL"
    if csv_path:
        return validate(normalise_headers(pd.read_csv(csv_path))), f"File adapter: {csv_path}"
    return validate(normalise_headers(pd.read_csv(io.StringIO(DEMO_CSV)))), "DEMONSTRATION DATA — no live bets or current fixtures"


def grade(row: pd.Series) -> str:
    if row.model_status.upper() != "ACTIVE" or row.data_quality.upper() not in {"GOOD", "EXCELLENT"}:
        return "PASS"
    if pd.isna(row.edge):
        return "PASS"
    if row.edge >= .07 and row.production_probability >= .70:
        return "A"
    if row.edge >= .05 and row.production_probability >= .62:
        return "B"
    if row.edge >= .03 and row.production_probability >= .55:
        return "C"
    return "PASS"


def enrich(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    valid_odds = data.bookmaker_odds > 1
    data["market_probability"] = np.where(valid_odds, 1 / data.bookmaker_odds, np.nan)
    data["edge"] = data.production_probability - data.market_probability
    data["expected_value"] = np.where(valid_odds, data.production_probability * data.bookmaker_odds - 1, np.nan)
    data["fair_odds"] = 1 / data.production_probability
    data["grade"] = data.apply(grade, axis=1)
    data["risk"] = np.select(
        [data.grade.eq("A"), data.grade.eq("B"), data.grade.eq("C")],
        ["Low", "Medium", "High"], default="Avoid",
    )
    data["fixture"] = data.home_team + " v " + data.away_team
    return data


def betting_board(data: pd.DataFrame) -> None:
    st.subheader("Betting Board")
    c1, c2, c3 = st.columns(3)
    leagues = c1.multiselect("League", sorted(data.competition.unique()))
    markets = c2.multiselect("Market", sorted(data.market.unique()))
    grades = c3.multiselect("Grade", ["A", "B", "C", "PASS"], default=["A", "B", "C"])
    view = data[data.grade.isin(grades)]
    if leagues:
        view = view[view.competition.isin(leagues)]
    if markets:
        view = view[view.market.isin(markets)]
    a, b, c, d = st.columns(4)
    a.metric("A picks", int(view.grade.eq("A").sum()))
    b.metric("B picks", int(view.grade.eq("B").sum()))
    c.metric("Qualified", int(view.grade.isin(["A", "B", "C"]).sum()))
    d.metric("Fixtures", view.match_id.nunique())
    shown = view[["grade", "date", "competition", "fixture", "market", "production_probability",
                  "fair_odds", "bookmaker_odds", "edge", "expected_value", "risk"]].sort_values(
        ["grade", "edge"], ascending=[True, False]
    )
    st.dataframe(shown, use_container_width=True, hide_index=True, column_config={
        "production_probability": st.column_config.ProgressColumn("Model %", min_value=0, max_value=1, format="%.1f%%"),
        "edge": st.column_config.NumberColumn("Edge", format="%.1f%%"),
        "expected_value": st.column_config.NumberColumn("EV", format="%.1f%%"),
        "fair_odds": st.column_config.NumberColumn("Fair", format="%.2f"),
        "bookmaker_odds": st.column_config.NumberColumn("Book", format="%.2f"),
    })
    st.info("Grades are deterministic presentation controls. PASS means no recommendation, not a prediction failure.")


def match_analysis(data: pd.DataFrame) -> None:
    st.subheader("Match Analysis")
    label = st.selectbox("Fixture", data.fixture.drop_duplicates().tolist())
    rows = data[data.fixture.eq(label)].sort_values("production_probability", ascending=False)
    first = rows.iloc[0]
    st.markdown(f"### {label}")
    st.caption(f"{first.competition} • {first.date:%d %b %Y} • Match ID {first.match_id}")
    for _, row in rows.iterrows():
        with st.container(border=True):
            a, b, c, d, e = st.columns(5)
            a.metric(row.market, f"{row.production_probability:.1%}", f"Grade {row.grade}")
            b.metric("Base", f"{row.base_probability:.1%}")
            c.metric("Fair odds", f"{row.fair_odds:.2f}")
            d.metric("Bookmaker", "—" if pd.isna(row.bookmaker_odds) else f"{row.bookmaker_odds:.2f}")
            e.metric("Edge", "—" if pd.isna(row.edge) else f"{row.edge:.1%}")
            st.write(f"**Risk:** {row.risk} · **Data quality:** {row.data_quality} · **Model:** {row.model_status}")
            if "justification" in rows.columns and pd.notna(row.get("justification")):
                st.write(row.justification)


def model_health(data: pd.DataFrame) -> None:
    st.subheader("Model Health")
    checks = {
        "Duplicate Match ID/market rows": int(data.duplicated(["match_id", "market"]).sum()),
        "Invalid probabilities": int((~data.production_probability.between(0, 1)).sum()),
        "Missing teams": int((data.home_team.eq("") | data.away_team.eq("")).sum()),
        "Rows without odds": int(data.bookmaker_odds.isna().sum()),
    }
    blocking = sum(v for k, v in checks.items() if k != "Rows without odds")
    st.metric("Current adapter status", "PASS" if blocking == 0 else "CHECK")
    st.table(pd.DataFrame([{"Control": k, "Count": v} for k, v in checks.items()]))
    st.markdown("#### Historical control contract")
    st.table(pd.DataFrame([
        ["Historical rows", "13,988"], ["Model eligible", "12,216"],
        ["Baseline exclusions", "46"], ["Prediction eligible", "12,170"],
        ["Bookmaker prices in core model", "NO"], ["Historical data modified", "NO"],
    ], columns=["Control", "Signed-off value"]))


st.set_page_config(page_title="Football Model Centre", page_icon="⚽", layout="wide")
st.title("⚽ Football Model Centre")
st.caption("Premier League • Championship • League One • League Two")
with st.sidebar:
    page = st.radio("Navigation", ["Betting Board", "Match Analysis", "Model Health"])
    st.divider()
    st.caption("V1.0.1 • self-contained deployment build")

try:
    source, source_note = load_predictions()
    predictions = enrich(source)
except Exception as exc:
    st.error(f"Data validation failed: {exc}")
    st.stop()

st.caption(source_note)
if page == "Betting Board":
    betting_board(predictions)
elif page == "Match Analysis":
    match_analysis(predictions)
else:
    model_health(predictions)
