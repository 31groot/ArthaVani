import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
from finance_agent.mcp_client import PersonalFinanceMCPClient
from personal_finance_mcp import server
from personal_finance_mcp.database import seed_database
from personal_finance_mcp.quotes import QuoteLookupError
from personal_finance_mcp.service import PersonalFinanceService

class PersonalFinanceToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "finance.db"
        seed_database(database_path)
        self.service = PersonalFinanceService(database_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_get_account_balance(self) -> None:
        result = self.service.get_account_balance("checking")
        self.assertEqual(result["account_type"], "checking")
        self.assertEqual(result["balance"], 2486.75)

    def test_get_transaction_history(self) -> None:
        result = self.service.get_transaction_history("credit_card", 2)
        self.assertEqual(len(result["transactions"]), 2)
        self.assertEqual(result["transactions"][0]["date"], "2026-08-21")

    def test_get_portfolio_summary(self) -> None:
        result = self.service.get_portfolio_summary()
        self.assertEqual(len(result["holdings"]), 3)
        self.assertGreater(result["total_market_value"], 0)

    def test_get_expense_breakdown(self) -> None:
        result = self.service.get_expense_breakdown("this_month")
        self.assertEqual(result["period"], "this_month")
        self.assertGreater(result["total_expenses"], 0)
        self.assertIn("Groceries", {item["category"] for item in result["categories"]})

    @patch("personal_finance_mcp.quotes.yf.Ticker")
    def test_get_stock_quote(self, ticker_factory: MagicMock) -> None:
        instrument = ticker_factory.return_value
        instrument.history.return_value = pd.DataFrame(
            {"Close": [224.50, 226.25]},
            index=pd.to_datetime(["2026-08-20", "2026-08-21"]),
        )
        instrument.get_history_metadata.return_value = {
            "currency": "USD", "regularMarketTime": 1_787_299_200,
        }
        instrument.get_info.return_value = {"longName": "Apple Inc.", "currency": "USD"}

        result = self.service.get_stock_quote("aapl")

        ticker_factory.assert_called_once_with("AAPL")
        self.assertEqual(result["ticker"], "AAPL")
        self.assertEqual(result["company_name"], "Apple Inc.")
        self.assertEqual(result["latest_price"], 226.25)
        self.assertEqual(result["previous_close"], 224.50)
        self.assertEqual(result["change"], 1.75)
        self.assertEqual(result["currency"], "USD")
        self.assertIn("data_timestamp", result)

    def test_mcp_server_exposes_exactly_five_tools_and_dispatches(self) -> None:
        async def verify() -> tuple[set[str], dict[str, object]]:
            client = PersonalFinanceMCPClient()
            try:
                await client.connect()

                tools = await client.discover_tools()
                names = {tool.name for tool in tools}

                result = await client.session.call_tool(
                    "get_account_balance",
                    {"account_type": "checking"},
                )

                payload = json.loads(result.content[0].text)
                return names, payload
            finally:
                await client.aclose()

        names, payload = asyncio.run(verify())

        self.assertEqual(
            names,
            {
                "get_account_balance",
                "get_transaction_history",
                "get_portfolio_summary",
                "get_expense_breakdown",
                "get_stock_quote",
            },
        )
        self.assertEqual(payload["account_type"], "checking")
        self.assertFalse(payload.get("error"))

    @patch("personal_finance_mcp.quotes.yf.Ticker")
    def test_invalid_inputs_have_useful_errors(self, ticker_factory: MagicMock) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid account_type"):
            self.service.get_account_balance("brokerage")
        with self.assertRaisesRegex(ValueError, "n must be"):
            self.service.get_transaction_history("checking", 0)
        with self.assertRaisesRegex(ValueError, "Invalid period"):
            self.service.get_expense_breakdown("quarter")
        with self.assertRaisesRegex(ValueError, "valid Yahoo Finance symbol"):
            self.service.get_stock_quote("BAD SYMBOL")

        ticker_factory.return_value.history.side_effect = RuntimeError("HTTP 429 rate limit")
        with self.assertRaisesRegex(QuoteLookupError, "rate limited"):
            self.service.get_stock_quote("AAPL")


if __name__ == "__main__":
    unittest.main()
