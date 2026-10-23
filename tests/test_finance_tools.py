import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import requests

from finance_agent.providers.market import market_status
from finance_agent.providers.watchlist import WatchlistStore


import uuid

import pytest

from finance_agent.persistence import (
    db_connection,
    initialize_database,
)

class FinanceToolSupportTests(unittest.TestCase):

    @pytest.mark.postgres
    def test_watchlist_store_add_list_remove(self) -> None:
        initialize_database()

        user_id = f"watchlist-test-{uuid.uuid4().hex}"
        email = f"{user_id}@example.com"
        store = WatchlistStore()

        # Create a valid user for the foreign-key constraint.
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO arthavani_users
                        (id, email, password_hash)
                    VALUES (%s, %s, %s)
                    """,
                    (user_id, email, "test-password-hash"),
                )
            conn.commit()

        try:
            added = store.add("TCS.NS", user_id)

            self.assertTrue(added["added"])
            self.assertEqual(added["ticker"], "TCS.NS")

            items = store.list_for_user(user_id)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["ticker"], "TCS.NS")

            removed = store.remove("TCS.NS", user_id)

            self.assertTrue(removed)
            self.assertEqual(store.list_for_user(user_id), [])

        finally:
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM arthavani_users WHERE id = %s",
                        (user_id,),
                    )
                conn.commit()

    def test_market_status_has_expected_shape(self) -> None:
        market_time = datetime(
            2026, 10, 6, 10, 0,
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
            2026, 10, 6, 10, 0,
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