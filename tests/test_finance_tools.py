
import tempfile
import unittest
from pathlib import Path

from finance_agent.providers.watchlist import WatchlistStore
from finance_agent.providers.market import market_status


class FinanceToolSupportTests(unittest.TestCase):
    def test_watchlist_store_add_list_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WatchlistStore(str(Path(tmp) / "watchlist.db"))

            alert = store.add("TCS.NS", "above", 4000)
            self.assertEqual(alert["ticker"], "TCS.NS")
            self.assertEqual(len(store.list_active()), 1)

            self.assertTrue(store.remove(alert["id"]))
            self.assertEqual(store.list_active(), [])

    def test_market_status_has_expected_shape(self) -> None:
        result = market_status()
        self.assertIn("exchange", result)
        self.assertIn("segment", result)
        self.assertIn("open", result)


if __name__ == "__main__":
    unittest.main()
