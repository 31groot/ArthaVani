
import tempfile
import unittest
from pathlib import Path

from finance_agent.providers.watchlist import WatchlistStore
from finance_agent.providers.market import market_status


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
        result = market_status()
        self.assertIn("exchange", result)
        self.assertIn("segment", result)
        self.assertIn("open", result)


if __name__ == "__main__":
    unittest.main()
