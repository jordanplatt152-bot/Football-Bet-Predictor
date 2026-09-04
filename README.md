# Football Model Centre V1.2.1.3

This release adds the live model-and-value feed, independent candidate expiry, a five-minute dashboard refresh and separate `Live Value Candidates` / `All Model Markets` views.

## Safety contract

- Read-only Streamlit UI; no betting-order capability.
- Feed contract `1.1` with exactly 33 columns.
- Candidates require an ACTIVE model, PASS data, A/B/C model and price grades, a price no more than ten minutes old and both capture/current time strictly before the pre-match cutoff. Betfair available liquidity is displayed for information only and never affects candidate status.
- Streamlit can downgrade a feed candidate but never promote a feed non-candidate.
- Delayed prices require manual confirmation.

## Apps Script deployment

1. Keep a backup of the previous Streamlit bridge.
2. Replace it with the complete `Streamlit_Value_Bridge_V1.0.11.gs` file. Retain only one active `doGet` across the Apps Script project.
3. Preserve the existing `STREAMLIT_FEED_TOKEN` Script Property. Never paste its value into logs or chat.
4. Run `runStreamlitValueBridgeV1011Preflight`. Require both source sheets, four rows per eligible fixture, zero integrity errors, zero writes and `FINAL STATUS: PASS`.
5. Deploy the existing web app as a **new version**. Keep the existing deployment and URL.
6. Open the existing authenticated URL privately. Confirm the first CSV row contains 33 headers and `feed_contract_version` is `1.1`.

## Streamlit deployment

1. Replace the repository-root `app.py` and `requirements.txt`; add `value_feed.py` from this package.
2. Preserve the existing `PREDICTIONS_CSV_URL` secret exactly. Its value must be only the tokenised URL—do not include `PREDICTIONS_CSV_URL =` in the value.
3. Commit and push. Wait for Streamlit Cloud to redeploy.
4. Confirm Connection status shows `LIVE_URL`, not `DEMO`.
5. Confirm current candidates appear only under `Live Value Candidates`; rejected/stale markets remain under `All Model Markets` with their reason.

## Acceptance sequence

1. Populate current fixtures and run the signed-off model-market population.
2. Capture Betfair prices before the ten-minute pre-match cutoff and complete the controlled price write.
3. Disable the remote write switch.
4. Run V1.0.10 controlled value publication and disable its write switch.
5. Confirm Streamlit calculations match V1.0.10. Do not refresh the prices; after ten minutes plus the next five-minute dashboard rerun, confirm those candidates become `STALE`.

## Rollback

Restore the V1.1.1 Streamlit root files and select the previous Apps Script deployment version. The workbook and signed-off V1.0.10 value layer require no rollback because this release does not modify them.

## V1.2.1 display correction

Table percentages are converted from probability fractions solely for display. For example, a model probability of `0.8269` is shown as `82.7%`, while the underlying value remains `0.8269` for validation and safety calculations. Edge and EV follow the same presentation rule. Stale rows remain visible only in All Model Markets and are never promoted into Live Value Candidates.

## Local verification

```bash
python -m unittest discover -s tests -v
python -m py_compile app.py value_feed.py
```


## V1.2.1.3 liquidity-independent consistency update
- Removes liquidity from candidate eligibility and rejection logic.
- Removes LOW_LIQUIDITY / LIQUIDITY_BELOW_50 as dashboard decision states.
- Retains available liquidity as an informational display field only.
- Preserves freshness, pre-match cutoff, model/data and value-grade controls.


## V1.2.1.3 UI clarity and legacy-metadata cleanup
- Removes legacy liquidity rejection metadata before dashboard safety output.
- Keeps dashboard status/rejection reasons internal for safety and Model Health diagnostics rather than showing them in normal betting-board tables or Match Analysis.
- Presents `market` as `Model Selection` so mixed Over/Under sides are clearly understood as the model-favoured side of each market family.
- Does not change market-selection mathematics: an Over 3.5 probability below 50% continues to select Under 3.5 at the complementary probability.


## V1.2.1.3 model-first decision clarity
- Exchange fractional prices are displayed without the approximation marker (`~`).
- Price age is displayed as `HH:MM:SS`; the underlying timestamp and ten-minute freshness gate are unchanged.
- Feed contract 1.2 adds read-only `home_expected_goals`, `away_expected_goals`, and `expected_total_goals`.
- Live Value Candidates includes a concise Model Rationale derived only from model probability and xG evidence.
- Match Analysis exposes Home xG, Away xG, Total xG, then separately labels Price Grade / Edge / EV as value confirmation.
- Betfair price, liquidity, edge, EV and price grade are never inputs to the rationale generator.
- No model mathematics, candidate thresholds, liquidity independence, cutoff/freshness rules, workbook writes, or betting capability are changed.

## V1.2.1.4 UI improvement
- Adds a UK-local 24-hour `Kickoff` display derived from the existing `event_commence_utc` field.
- Adds Betting Board sorting for earliest kickoff, latest kickoff, or the existing model/value ranking.
- Displays kickoff time in Match Analysis.
- Presentation only: no model, candidate-eligibility, price/value, cutoff, or liquidity logic is changed.
