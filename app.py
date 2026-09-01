import streamlit as st

from dashboard.data import load_predictions
from dashboard.metrics import enrich_predictions
from dashboard.ui import render_betting_board, render_match_analysis, render_model_health


st.set_page_config(page_title="Football Model Centre", page_icon="⚽", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem; max-width: 1500px;}
    [data-testid="stMetric"] {background:#111827; border-radius:10px; padding:14px;}
    [data-testid="stMetric"] label, [data-testid="stMetric"] div {color:white;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("⚽ Football Model Centre")
st.caption("Premier League • Championship • League One • League Two")

with st.sidebar:
    st.header("Navigation")
    page = st.radio("Page", ["Betting Board", "Match Analysis", "Model Health"], label_visibility="collapsed")
    st.divider()
    st.caption("Dashboard V1.0.0 • Base model preserved • market comparison isolated")

try:
    frame, source_note = load_predictions()
    data = enrich_predictions(frame)
except Exception as exc:
    st.error(f"Data validation failed: {exc}")
    st.stop()

st.caption(source_note)

if page == "Betting Board":
    render_betting_board(data)
elif page == "Match Analysis":
    render_match_analysis(data)
else:
    render_model_health(data)
