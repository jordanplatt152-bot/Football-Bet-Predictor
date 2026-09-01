from __future__ import annotations

import pandas as pd
import streamlit as st


def _pct(value: float) -> str:
    return "—" if pd.isna(value) else f"{value:.1%}"


def render_betting_board(data: pd.DataFrame) -> None:
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


def render_match_analysis(data: pd.DataFrame) -> None:
    st.subheader("Match Analysis")
    fixtures = data[["match_id", "fixture"]].drop_duplicates()
    label = st.selectbox("Fixture", fixtures.fixture.tolist())
    rows = data[data.fixture.eq(label)].sort_values("production_probability", ascending=False)
    first = rows.iloc[0]
    st.markdown(f"### {label}")
    st.caption(f"{first.competition} • {first.date:%d %b %Y} • Match ID {first.match_id}")
    for _, row in rows.iterrows():
        with st.container(border=True):
            a, b, c, d, e = st.columns(5)
            a.metric(row.market, _pct(row.production_probability), f"Grade {row.grade}")
            b.metric("Base", _pct(row.base_probability))
            c.metric("Fair odds", f"{row.fair_odds:.2f}")
            d.metric("Bookmaker", "—" if pd.isna(row.bookmaker_odds) else f"{row.bookmaker_odds:.2f}")
            e.metric("Edge", _pct(row.edge))
            st.write(f"**Risk:** {row.risk} · **Data quality:** {row.data_quality} · **Model:** {row.model_status}")
            if "justification" in rows.columns and pd.notna(row.get("justification")):
                st.write(row.justification)


def render_model_health(data: pd.DataFrame) -> None:
    st.subheader("Model Health")
    checks = {
        "Duplicate Match IDs": int(data[["match_id", "market"]].duplicated().sum()),
        "Invalid probabilities": int((~data.production_probability.between(0, 1)).sum()),
        "Missing teams": int((data.home_team.eq("") | data.away_team.eq("")).sum()),
        "Rows without odds": int(data.bookmaker_odds.isna().sum()),
    }
    status = "PASS" if sum(v for k, v in checks.items() if k != "Rows without odds") == 0 else "CHECK"
    st.metric("Current adapter status", status)
    st.table(pd.DataFrame([{"Control": k, "Count": v} for k, v in checks.items()]))
    st.markdown("#### Historical control contract")
    st.table(pd.DataFrame([
        ["Historical rows", "13,988"], ["Model eligible", "12,216"],
        ["Baseline exclusions", "46"], ["Prediction eligible", "12,170"],
        ["Bookmaker prices in core model", "NO"], ["Historical data modified", "NO"],
    ], columns=["Control", "Signed-off value"]))
