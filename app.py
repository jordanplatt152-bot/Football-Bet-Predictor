from __future__ import annotations

import os
from datetime import timedelta
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from value_feed import (
    apply_dashboard_safety, select_adapter, sort_candidates,
    validate_feed, with_display_percentages,
)


def setting(name: str) -> tuple[str, str]:
    value = os.getenv(name, "").strip()
    if value:
        return value, "environment"
    try:
        value = str(st.secrets.get(name, "")).strip()
        return value, "Streamlit secrets" if value else "missing"
    except Exception:
        return "", "missing"


def demo_data(now: pd.Timestamp) -> pd.DataFrame:
    capture = now - timedelta(minutes=5)
    commence = now + timedelta(hours=6)
    cutoff = commence - timedelta(minutes=10)
    common = {
        "feed_contract_version": "1.1", "feed_generated_utc": now.isoformat(),
        "match_id": "DEMO-2026-FOOTBALL", "date": now.date().isoformat(),
        "competition": "Championship", "home_team": "Demonstration FC", "away_team": "Example United",
        "base_probability": .65, "production_probability": .65, "model_score": 80,
        "model_grade": "B", "data_quality": "PASS", "model_status": "ACTIVE",
        "exchange_back_odds": 1.90, "effective_exchange_odds": 1.882,
        "bookmaker_odds": 1.882, "fractional_odds": "~10/11",
        "price_source": "DEMONSTRATION ONLY", "available_liquidity_gbp": 100,
        "price_timestamp_utc": capture.isoformat(), "event_commence_utc": commence.isoformat(),
        "pre_match_cutoff_utc": cutoff.isoformat(), "implied_probability": 1 / 1.882,
        "probability_edge": .65 - 1 / 1.882, "expected_value": .65 * 1.882 - 1,
        "price_grade": "B", "stored_decision": "PASS", "feed_price_age_minutes": 5,
        "feed_status": "NO_VALUE", "feed_candidate": False,
        "rejection_reasons": "DEMONSTRATION_ONLY", "justification": "Illustrative row; never a live candidate.",
    }
    return pd.DataFrame([{**common, "market": "Over 1.5"}])


@st.cache_data(ttl=300, show_spinner="Refreshing model and value feed…")
def load_configured_feed(mode: str, csv_url: str, csv_path: str) -> pd.DataFrame:
    if mode == "LIVE_URL":
        return pd.read_csv(csv_url)
    if mode == "LIVE_FILE":
        return pd.read_csv(csv_path)
    raise ValueError("No configured live adapter")


def candidate_table(rows: pd.DataFrame) -> pd.DataFrame:
    columns = ["price_grade", "model_grade", "fixture", "market", "fractional_odds",
               "effective_exchange_odds", "model_percent_display", "edge_percent_display",
               "ev_percent_display", "available_liquidity_gbp", "dashboard_price_age_minutes"]
    return rows[columns]


def betting_board(data: pd.DataFrame, demo: bool) -> None:
    st.subheader("Live Value Candidates")
    live = sort_candidates(data[data.dashboard_candidate])
    if demo:
        st.info("Demonstration mode cannot produce live value candidates.")
    elif live.empty:
        st.info("No markets currently satisfy every model, value, freshness and pre-match control.")
    else:
        st.dataframe(candidate_table(live), use_container_width=True, hide_index=True, column_config={
            "market": "Model Selection",
            "fractional_odds": "Exchange price",
            "effective_exchange_odds": st.column_config.NumberColumn("Effective decimal", format="%.3f"),
            "model_percent_display": st.column_config.NumberColumn("Model %", format="%.1f%%"),
            "edge_percent_display": st.column_config.NumberColumn("Edge %", format="%.1f%%"),
            "ev_percent_display": st.column_config.NumberColumn("EV %", format="%.1f%%"),
            "available_liquidity_gbp": st.column_config.NumberColumn("Liquidity", format="£%.2f"),
            "dashboard_price_age_minutes": st.column_config.NumberColumn("Age (min)", format="%.1f"),
        })

    st.subheader("All Model Markets")
    st.caption("Model Selection shows the model-favoured side for each market family; it may therefore switch between Over and Under.")
    c1, c2 = st.columns(2)
    leagues = c1.multiselect("League", sorted(data.competition.unique()))
    markets = c2.multiselect("Model Selection", sorted(data.market.unique()))
    view = data
    if leagues: view = view[view.competition.isin(leagues)]
    if markets: view = view[view.market.isin(markets)]
    st.dataframe(view[["fixture", "market", "model_grade", "price_grade", "fractional_odds",
                       "effective_exchange_odds", "model_percent_display", "edge_percent_display",
                       "ev_percent_display", "available_liquidity_gbp", "dashboard_price_age_minutes"]],
                 use_container_width=True, hide_index=True,
                 column_config={
                     "market": "Model Selection",
                     "fractional_odds": "Exchange price",
                     "effective_exchange_odds": st.column_config.NumberColumn("Effective decimal", format="%.3f"),
                     "model_percent_display": st.column_config.NumberColumn("Model %", format="%.1f%%"),
                     "edge_percent_display": st.column_config.NumberColumn("Edge %", format="%.1f%%"),
                     "ev_percent_display": st.column_config.NumberColumn("EV %", format="%.1f%%"),
                     "available_liquidity_gbp": st.column_config.NumberColumn("Liquidity", format="£%.2f"),
                     "dashboard_price_age_minutes": st.column_config.NumberColumn("Age (min)", format="%.1f"),
                 })


def match_analysis(data: pd.DataFrame) -> None:
    st.subheader("Match Analysis")
    fixture = st.selectbox("Fixture", data.fixture.drop_duplicates().tolist())
    rows = data[data.fixture.eq(fixture)]
    for _, row in rows.iterrows():
        with st.container(border=True):
            st.markdown(f"### Model Selection: {row.market}")
            a, b, c, d = st.columns(4)
            a.metric("Model", f"{row.production_probability:.1%}", f"Grade {row.model_grade}")
            b.metric("Exchange", row.fractional_odds or "—", f"Effective {row.effective_exchange_odds:.3f}" if pd.notna(row.effective_exchange_odds) else "Unpriced")
            c.metric("Edge", f"{row.probability_edge:.1%}" if pd.notna(row.probability_edge) else "—")
            d.metric("EV", f"{row.expected_value:.1%}" if pd.notna(row.expected_value) else "—", f"Price grade {row.price_grade}")
            st.write(f"Liquidity: £{row.available_liquidity_gbp:.2f} · Price age: {row.dashboard_price_age_minutes:.1f} min · Cutoff: {row.pre_match_cutoff_utc}")


def model_health(data: pd.DataFrame, now: pd.Timestamp) -> None:
    st.subheader("Model Health")
    a, b, c, d = st.columns(4)
    a.metric("Contract", str(data.feed_contract_version.iloc[0]))
    b.metric("Fixtures", data.match_id.nunique())
    c.metric("Market rows", len(data))
    d.metric("Live candidates", int(data.dashboard_candidate.sum()))
    counts = data.dashboard_status.value_counts().rename_axis("Status").reset_index(name="Rows")
    st.table(counts)
    st.caption(f"Feed checked {now:%Y-%m-%d %H:%M:%S UTC} · Generated {data.feed_generated_utc.max()}")
    st.markdown("Historical controls: 13,988 rows · 12,170 prediction eligible · bookmaker prices in core model: NO · historical data modified: NO")


st.set_page_config(page_title="Football Model Centre", page_icon="⚽", layout="wide")
st_autorefresh(interval=300_000, limit=None, key="football-value-refresh")
now_utc = pd.Timestamp.now(tz="UTC")
st.title("⚽ Football Model Centre")
st.caption("Premier League • Championship • League One • League Two")
st.warning("Delayed exchange prices. Confirm the current market manually before acting. This dashboard never places bets.")

with st.sidebar:
    page = st.radio("Navigation", ["Betting Board", "Match Analysis", "Model Health"])
    if st.button("↻ Refresh Live Data", use_container_width=True):
        st.cache_data.clear(); st.rerun()
    st.caption("V1.2.1.2 · liquidity-independent · simplified decision display · automatic five-minute safety refresh")

csv_url, url_source = setting("PREDICTIONS_CSV_URL")
csv_path, path_source = setting("PREDICTIONS_CSV_PATH")
mode = select_adapter(csv_url, csv_path)
try:
    raw = demo_data(now_utc) if mode == "DEMO" else load_configured_feed(mode, csv_url, csv_path)
    data = with_display_percentages(apply_dashboard_safety(validate_feed(raw), now_utc))
except Exception as exc:
    st.error(f"CHECK — configured feed could not be validated: {exc}")
    st.stop()

with st.sidebar.expander("Connection status", expanded=mode == "DEMO"):
    st.write(f"**Feed mode:** {mode}")
    st.write(f"**Configuration source:** {url_source if mode == 'LIVE_URL' else path_source if mode == 'LIVE_FILE' else 'none'}")
    st.write(f"**Endpoint host:** {urlparse(csv_url).hostname if mode == 'LIVE_URL' else 'Not configured'}")
    st.write(f"**Fixtures loaded:** {data.match_id.nunique()}")
    st.write(f"**Market rows loaded:** {len(data)}")
    st.write(f"**Checked:** {now_utc:%Y-%m-%d %H:%M:%S UTC}")
    st.caption("Credentials, query strings and complete URLs are never displayed.")

if mode == "DEMO":
    st.caption("DEMONSTRATION DATA — no live bets or current fixtures")
else:
    st.caption("LIVE VALUE FEED — independent dashboard safety checks active")

if page == "Betting Board":
    betting_board(data, mode == "DEMO")
elif page == "Match Analysis":
    match_analysis(data)
else:
    model_health(data, now_utc)
