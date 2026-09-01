# Football Model Centre — Streamlit V1.0.0

Remote decision-support dashboard for the Premier League, Championship, League One and League Two.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Without configuration the app loads fictional, clearly labelled demonstration rows. It must not be used for live betting in demo mode.

## Connect production predictions

Set either:

- `PREDICTIONS_CSV_URL` — a published/export CSV endpoint; or
- `PREDICTIONS_CSV_PATH` — a local CSV file.

Required columns:

`match_id,date,competition,home_team,away_team,market,base_probability,production_probability,bookmaker_odds,data_quality,model_status`

Optional column: `justification`.

Probabilities may be decimals (0–1) or percentages (0–100). Decimal odds must be greater than 1. The application validates duplicate Match ID/market pairs, dates and probability ranges before displaying selections. Multiple markets for the same fixture are valid.

## Model controls

- Base and production probabilities remain separate.
- Bookmaker odds are used only for market comparison.
- Grades are deterministic presentation controls.
- Current grades: A = edge ≥7% and probability ≥70%; B = ≥5% and ≥62%; C = ≥3% and ≥55%; otherwise PASS.
- Any non-ACTIVE model row or sub-GOOD data quality is forced to PASS.
- Missing bookmaker odds produce no edge and no qualified grade.

## Deployment

The project is ready for Streamlit Community Cloud or another Python host. Add the environment variable in the host's secrets/configuration rather than committing private URLs or credentials.
