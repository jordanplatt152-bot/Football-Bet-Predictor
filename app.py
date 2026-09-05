from __future__ import annotations

import os
from html import escape
from datetime import timedelta
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from value_feed import (
    apply_dashboard_safety, select_adapter, sort_candidates, sort_dashboard_rows,
    validate_feed, with_display_percentages, with_fixture_kickoff_display, with_qol_display, filter_dashboard_date,
    filter_live_candidates_by_bet_type, fixture_summary_rows,
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
        "feed_contract_version": "1.2", "feed_generated_utc": now.isoformat(),
        "match_id": "DEMO-2026-FOOTBALL", "date": now.date().isoformat(),
        "competition": "Championship", "home_team": "Demonstration FC", "away_team": "Example United",
        "home_expected_goals": 1.30, "away_expected_goals": 1.10, "expected_total_goals": 2.40,
        "base_probability": .65, "production_probability": .65, "model_score": 80,
        "model_grade": "B", "data_quality": "PASS", "model_status": "ACTIVE",
        "exchange_back_odds": 1.90, "effective_exchange_odds": 1.882,
        "bookmaker_odds": 1.882, "fractional_odds": "10/11",
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
    columns = ["price_grade", "model_grade", "date_display", "kickoff_display", "fixture", "market", "model_rationale", "exchange_price_display",
               "effective_exchange_odds", "model_percent_display", "edge_percent_display",
               "available_liquidity_gbp", "price_age_clock"]
    return rows[columns]


def betting_board(data: pd.DataFrame, demo: bool) -> None:
    cdate, csort = st.columns(2)
    date_mode = cdate.selectbox("Date", ["All dates", "Today", "Tomorrow"], index=0)
    sort_mode = csort.selectbox(
        "Sort by",
        ["Kickoff — earliest first", "Kickoff — latest first", "Model/value ranking"],
        index=0,
    )
    filtered = filter_dashboard_date(data, date_mode, now_utc)

    st.subheader("Live Value Candidates")
    live_base = filtered[filtered.dashboard_candidate].copy()
    bet_type_options = ["All"] + sorted(live_base["market"].dropna().astype(str).unique().tolist())
    bet_type = st.selectbox("Bet Type", bet_type_options, index=0, key="live_value_bet_type")
    live = filter_live_candidates_by_bet_type(live_base, bet_type)
    live = sort_dashboard_rows(live, sort_mode)
    if demo:
        st.info("Demonstration mode cannot produce live value candidates.")
    elif live.empty:
        st.info("No markets currently satisfy every model, value, freshness and pre-match control.")
    else:
        st.dataframe(candidate_table(live), use_container_width=True, hide_index=True, column_config={
            "date_display": "Date",
            "kickoff_display": "Kickoff",
            "market": "Model Selection",
            "model_rationale": "Model Rationale",
            "exchange_price_display": "Exchange price",
            "effective_exchange_odds": st.column_config.NumberColumn("Effective decimal", format="%.3f"),
            "model_percent_display": st.column_config.NumberColumn("Model %", format="%.1f%%"),
            "edge_percent_display": st.column_config.NumberColumn("Edge %", format="%.1f%%"),
            "available_liquidity_gbp": st.column_config.NumberColumn("Liquidity", format="£%.2f"),
            "price_age_clock": "Age",
        })


    summaries = fixture_summary_rows(filtered, sort_mode)
    with st.expander(f"Fixture Overview — {len(summaries)} fixtures", expanded=False):
        st.caption("Model-first fixture summary. Expand when you want fixture-level context.")
        if not summaries:
            st.info("No fixtures are available for the selected date.")
        st.markdown(
            """
            <style>
            .fixture-card-compact {
                border: 1px solid rgba(49, 51, 63, 0.18);
                border-radius: 0.55rem;
                padding: 0.58rem 0.72rem 0.52rem 0.72rem;
                margin-bottom: 0.55rem;
                line-height: 1.22;
            }
            .fixture-card-title {
                font-size: 1.02rem;
                font-weight: 700;
                margin-bottom: 0.18rem;
            }
            .fixture-card-meta {
                font-size: 0.76rem;
                opacity: 0.68;
                margin-bottom: 0.28rem;
            }
            .fixture-card-stats, .fixture-card-strongest {
                font-size: 0.82rem;
                margin-top: 0.16rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        fixture_columns = st.columns(3)
        for index, summary in enumerate(summaries):
            selections = " · ".join(
                f"{escape(str(market))} {probability:.1%} ({escape(str(grade))})"
                for market, probability, grade in summary["top_selections"]
            )
            card_html = (
                f'<div class="fixture-card-compact">'
                f'<div class="fixture-card-title">{escape(str(summary["fixture"]))}</div>'
                f'<div class="fixture-card-meta">{escape(str(summary["date"]))} · '
                f'{escape(str(summary["kickoff"]))} UK · {escape(str(summary["competition"]))}</div>'
                f'<div class="fixture-card-stats">Home xG <b>{summary["home_xg"]:.2f}</b> · '
                f'Away xG <b>{summary["away_xg"]:.2f}</b> · Total xG <b>{summary["total_xg"]:.2f}</b></div>'
                f'<div class="fixture-card-strongest"><b>Strongest:</b> {selections}</div>'
                f'</div>'
            )
            with fixture_columns[index % 3]:
                st.markdown(card_html, unsafe_allow_html=True)
    st.subheader("All Model Markets")
    st.caption("Model Selection shows the model-favoured side for each market family; it may therefore switch between Over and Under.")
    c1, c2, c3 = st.columns(3)
    leagues = c1.multiselect("League", sorted(filtered.competition.unique()))
    markets = c2.multiselect("Model Selection", sorted(filtered.market.unique()))
    kickoff_options = ["All times"] + sorted(filtered["kickoff_display"].dropna().astype(str).unique().tolist())
    kickoff_time = c3.selectbox("Kickoff time", kickoff_options, index=0, key="all_markets_kickoff_time")
    view = filtered
    if leagues: view = view[view.competition.isin(leagues)]
    if markets: view = view[view.market.isin(markets)]
    if kickoff_time != "All times":
        view = view[view.kickoff_display.eq(kickoff_time)]
    view = sort_dashboard_rows(view, sort_mode)
    st.dataframe(view[["date_display", "kickoff_display", "fixture", "market", "model_grade", "price_grade", "exchange_price_display",
                       "effective_exchange_odds", "model_percent_display", "edge_percent_display",
                       "available_liquidity_gbp", "price_age_clock"]],
                 use_container_width=True, hide_index=True,
                 column_config={
                     "date_display": "Date",
                     "kickoff_display": "Kickoff",
                     "market": "Model Selection",
                     "model_rationale": "Model Rationale",
            "exchange_price_display": "Exchange price",
                     "effective_exchange_odds": st.column_config.NumberColumn("Effective decimal", format="%.3f"),
                     "model_percent_display": st.column_config.NumberColumn("Model %", format="%.1f%%"),
                     "edge_percent_display": st.column_config.NumberColumn("Edge %", format="%.1f%%"),
                     "available_liquidity_gbp": st.column_config.NumberColumn("Liquidity", format="£%.2f"),
                     "price_age_clock": "Age",
                 })


def match_analysis(data: pd.DataFrame) -> None:
    st.subheader("Match Analysis")
    fixture = st.selectbox("Fixture", data.fixture.drop_duplicates().tolist())
    rows = data[data.fixture.eq(fixture)].copy()
    if rows.empty:
        st.info("No model markets are available for this fixture.")
        return

    first = rows.iloc[0]
    date = first["date_display"]
    kickoff = first["kickoff_display"]
    competition = first["competition"]
    st.markdown(f"### {fixture}")
    st.caption(f"Date: {date} · Kickoff: {kickoff} UK · League: {competition}")
    st.markdown(
        f"Home xG **{first.home_expected_goals:.2f}** · "
        f"Away xG **{first.away_expected_goals:.2f}** · "
        f"Total xG **{first.expected_total_goals:.2f}**"
    )

    rows["ev_percent_display"] = rows["expected_value"] * 100
    comparison_columns = [
        "market", "model_percent_display", "model_grade",
        "exchange_price_display", "effective_exchange_odds",
        "edge_percent_display", "ev_percent_display", "price_grade",
        "available_liquidity_gbp", "price_age_clock",
    ]
    st.dataframe(
        rows[comparison_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            "market": "Model Selection",
            "model_percent_display": st.column_config.NumberColumn("Model %", format="%.1f%%"),
            "model_grade": "Model Grade",
            "exchange_price_display": "Exchange price",
            "effective_exchange_odds": st.column_config.NumberColumn("Effective decimal", format="%.3f"),
            "edge_percent_display": st.column_config.NumberColumn("Edge %", format="%.1f%%"),
            "ev_percent_display": st.column_config.NumberColumn("EV %", format="%.1f%%"),
            "price_grade": "Price Grade",
            "available_liquidity_gbp": st.column_config.NumberColumn("Liquidity", format="£%.2f"),
            "price_age_clock": "Age",
        },
    )

    with st.expander("Detailed rationale and cutoff information", expanded=False):
        for _, row in rows.iterrows():
            st.markdown(f"**{row.market} — Model rationale:** {row.model_rationale}")
            st.caption(
                f"Cutoff: {row.pre_match_cutoff_utc} · "
                f"Price source: {row.price_source} · "
                f"Liquidity (information only): £{row.available_liquidity_gbp:.2f}"
            )

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
    st.caption("V1.2.1.12 · compact match analysis · live value first · collapsible compact fixture grid · all-markets kickoff filter · live candidate bet-type filter · date + kickoff sorting · model-first decision clarity · liquidity-independent · automatic five-minute safety refresh")

csv_url, url_source = setting("PREDICTIONS_CSV_URL")
csv_path, path_source = setting("PREDICTIONS_CSV_PATH")
mode = select_adapter(csv_url, csv_path)
try:
    raw = demo_data(now_utc) if mode == "DEMO" else load_configured_feed(mode, csv_url, csv_path)
    data = with_fixture_kickoff_display(with_qol_display(with_display_percentages(apply_dashboard_safety(validate_feed(raw), now_utc))))
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
