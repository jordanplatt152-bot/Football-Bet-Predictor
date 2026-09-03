import unittest
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from value_feed import (
    REQUIRED_COLUMNS, apply_dashboard_safety, select_adapter,
    sort_candidates, validate_feed, with_display_percentages,
)


def valid_row(**changes):
    row = {
        "feed_contract_version": "1.1", "feed_generated_utc": "2026-09-02T08:05:00Z",
        "match_id": "2026-09-02-MILLWALL-WREXHAM", "date": "2026-09-02",
        "competition": "Championship", "home_team": "Millwall", "away_team": "Wrexham",
        "market": "BTTS No", "base_probability": 0.5459, "production_probability": 0.5459,
        "model_score": 59.18, "model_grade": "C", "data_quality": "PASS", "model_status": "ACTIVE",
        "exchange_back_odds": 2.18, "effective_exchange_odds": 2.1564, "bookmaker_odds": 2.1564,
        "fractional_odds": "6/5", "price_source": "Betfair Exchange delayed",
        "available_liquidity_gbp": 309.80, "price_timestamp_utc": "2026-09-02T08:00:00Z",
        "event_commence_utc": "2026-09-02T18:45:00Z", "pre_match_cutoff_utc": "2026-09-02T18:35:00Z",
        "implied_probability": 1 / 2.1564, "probability_edge": 0.5459 - 1 / 2.1564,
        "expected_value": 0.5459 * 2.1564 - 1, "price_grade": "A",
        "stored_decision": "VALUE CANDIDATE", "feed_price_age_minutes": 5,
        "feed_status": "VALUE_CANDIDATE", "feed_candidate": "TRUE", "rejection_reasons": "",
        "justification": "Fresh pre-match model and exchange value candidate.",
    }
    row.update(changes)
    return row


class FeedValidationTests(unittest.TestCase):
    def test_valid_contract_is_typed(self):
        result = validate_feed(pd.DataFrame([valid_row()]))
        self.assertEqual(set(REQUIRED_COLUMNS), set(result.columns))
        self.assertTrue(bool(result.loc[0, "feed_candidate"]))
        self.assertEqual(str(result.loc[0, "price_timestamp_utc"].tz), "UTC")
        self.assertAlmostEqual(result.loc[0, "effective_exchange_odds"], 2.1564)

    def test_missing_column_is_rejected(self):
        row = valid_row(); row.pop("market")
        with self.assertRaisesRegex(ValueError, "missing required columns: market"):
            validate_feed(pd.DataFrame([row]))

    def test_duplicate_market_is_rejected(self):
        with self.assertRaisesRegex(ValueError, r"duplicate match_id \+ market"):
            validate_feed(pd.DataFrame([valid_row(), valid_row()]))

    def test_invalid_probability_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid production_probability"):
            validate_feed(pd.DataFrame([valid_row(production_probability=1.01)]))

    def test_wrong_contract_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported feed contract"):
            validate_feed(pd.DataFrame([valid_row(feed_contract_version="1.0")]))

    def test_effective_alias_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "bookmaker_odds must equal effective_exchange_odds"):
            validate_feed(pd.DataFrame([valid_row(bookmaker_odds=2.0)]))


class DashboardSafetyTests(unittest.TestCase):
    def assess(self, row, now):
        return apply_dashboard_safety(validate_feed(pd.DataFrame([row])), pd.Timestamp(now)).iloc[0]

    def test_fresh_candidate_remains_candidate(self):
        result = self.assess(valid_row(price_timestamp_utc="2026-09-02T07:55:00.001Z"), "2026-09-02T08:05:00Z")
        self.assertTrue(bool(result.dashboard_candidate))
        self.assertEqual(result.dashboard_status, "VALUE_CANDIDATE")

    def test_ten_minutes_plus_one_millisecond_is_stale(self):
        result = self.assess(valid_row(price_timestamp_utc="2026-09-02T07:54:59.999Z"), "2026-09-02T08:05:00Z")
        self.assertFalse(bool(result.dashboard_candidate))
        self.assertEqual(result.dashboard_status, "STALE")

    def test_feed_non_candidate_cannot_be_upgraded(self):
        result = self.assess(valid_row(feed_candidate="FALSE", feed_status="NO_VALUE"), "2026-09-02T08:05:00Z")
        self.assertFalse(bool(result.dashboard_candidate))
        self.assertEqual(result.dashboard_status, "NO_VALUE")

    def test_exact_cutoff_is_post_cutoff(self):
        result = self.assess(valid_row(price_timestamp_utc="2026-09-02T18:34:00Z"), "2026-09-02T18:35:00Z")
        self.assertFalse(bool(result.dashboard_candidate))
        self.assertEqual(result.dashboard_status, "POST_CUTOFF")

    def test_liquidity_below_fifty_is_rejected(self):
        result = self.assess(valid_row(available_liquidity_gbp=49.99), "2026-09-02T08:05:00Z")
        self.assertFalse(bool(result.dashboard_candidate))
        self.assertEqual(result.dashboard_status, "LOW_LIQUIDITY")

    def test_future_timestamp_is_rejected(self):
        result = self.assess(valid_row(price_timestamp_utc="2026-09-02T08:05:00.001Z"), "2026-09-02T08:05:00Z")
        self.assertFalse(bool(result.dashboard_candidate))
        self.assertEqual(result.dashboard_status, "FUTURE_TIMESTAMP")

    def test_table_percentages_are_scaled_without_mutating_model_values(self):
        source = pd.DataFrame([{
            "production_probability": 0.8269,
            "probability_edge": 0.039,
            "expected_value": 0.0689,
        }])
        result = with_display_percentages(source)
        self.assertAlmostEqual(result.loc[0, "model_percent_display"], 82.69)
        self.assertAlmostEqual(result.loc[0, "edge_percent_display"], 3.9)
        self.assertAlmostEqual(result.loc[0, "ev_percent_display"], 6.89)
        self.assertAlmostEqual(result.loc[0, "production_probability"], 0.8269)


class AdapterAndOrderingTests(unittest.TestCase):
    def test_adapter_policy(self):
        self.assertEqual(select_adapter("https://example.test/feed", ""), "LIVE_URL")
        self.assertEqual(select_adapter("", "predictions.csv"), "LIVE_FILE")
        self.assertEqual(select_adapter("", ""), "DEMO")

    def test_candidates_sort_by_grade_then_ev_then_probability(self):
        rows = pd.DataFrame([
            {"price_grade": "B", "expected_value": .30, "production_probability": .80},
            {"price_grade": "A", "expected_value": .15, "production_probability": .60},
            {"price_grade": "A", "expected_value": .20, "production_probability": .55},
            {"price_grade": "A", "expected_value": .20, "production_probability": .70},
            {"price_grade": "C", "expected_value": .50, "production_probability": .90},
        ])
        result = sort_candidates(rows)
        self.assertEqual(result.index.tolist(), [3, 2, 1, 0, 4])


if __name__ == "__main__":
    unittest.main()
