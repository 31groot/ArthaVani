import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import requests

from finance_agent.providers.market import market_status
from finance_agent.providers.watchlist import WatchlistStore


class FinanceToolSupportTests(unittest.TestCase):
    def test_watchlist_store_add_list_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WatchlistStore(str(Path(tmp) / "watchlist.db"))

            added = store.add("TCS.NS", "alice")

            self.assertTrue(added["added"])
            self.assertEqual(added["ticker"], "TCS.NS")

            items = store.list_for_user("alice")

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["ticker"], "TCS.NS")

            removed = store.remove("TCS.NS", "alice")

            self.assertTrue(removed)
            self.assertEqual(store.list_for_user("alice"), [])

    def test_market_status_has_expected_shape(self) -> None:
        market_time = datetime(
            2026,
            10,
            6,
            10,
            0,
            tzinfo=ZoneInfo("Asia/Kolkata"),
        )

        with patch(
            "finance_agent.providers.market._trading_holidays",
            return_value={},
        ):
            result = market_status(at=market_time)

        self.assertIn("exchange", result)
        self.assertIn("segment", result)
        self.assertIn("open", result)

    def test_market_status_handles_nse_failure(self) -> None:
        market_time = datetime(
            2026,
            10,
            6,
            10,
            0,
            tzinfo=ZoneInfo("Asia/Kolkata"),
        )

        with patch(
            "finance_agent.providers.market._trading_holidays",
            side_effect=requests.RequestException("NSE unavailable"),
        ):
            result = market_status(at=market_time)

        self.assertIn("open", result)
        self.assertIsNone(result["open"])
        self.assertEqual(result["reason"], "status_unavailable")
        self.assertFalse(result["status_verified"])


if __name__ == "__main__":
    unittest.main()