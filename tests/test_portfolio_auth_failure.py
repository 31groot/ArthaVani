import unittest
from unittest.mock import patch

from finance_agent.tools import get_portfolio_risk, get_portfolio_summary


class RaisingGrowwProvider:
    def get_holdings(self):
        raise RuntimeError(
            "Authorisation failed. Your API token does not have the required permissions."
        )


class PortfolioAuthFailureTests(unittest.TestCase):
    def test_summary_returns_structured_failure(self):
        with patch(
            "finance_agent.tools.get_groww_provider",
            return_value=RaisingGrowwProvider(),
        ):
            result = get_portfolio_summary.invoke({})

        self.assertFalse(result["portfolio_data_available"])
        self.assertFalse(result["market_data_available"])
        self.assertIsNone(result["profit_loss"])
        self.assertEqual(result["valuation_basis"], "unavailable")
        self.assertIn("portfolio access failed", result["market_data_error"])

    def test_risk_returns_structured_failure(self):
        with patch(
            "finance_agent.tools.get_groww_provider",
            return_value=RaisingGrowwProvider(),
        ):
            result = get_portfolio_risk.invoke({})

        self.assertFalse(result["portfolio_data_available"])
        self.assertIsNone(result["concentration_hhi"])
        self.assertEqual(result["allocation_basis"], "unavailable")
        self.assertIn("portfolio access failed", result["market_data_error"])


if __name__ == "__main__":
    unittest.main()
