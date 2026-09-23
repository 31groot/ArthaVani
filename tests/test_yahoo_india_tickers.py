import unittest

from finance_agent.providers.yahoo import normalize_symbol


class YahooIndiaTickerTests(unittest.TestCase):
    def test_infosys_uses_nse_symbol(self):
        self.assertEqual(normalize_symbol("INFY"), "INFY.NS")
        self.assertEqual(normalize_symbol("Infosys"), "INFY.NS")

    def test_other_indian_symbols(self):
        self.assertEqual(normalize_symbol("TCS"), "TCS.NS")
        self.assertEqual(normalize_symbol("HDFC Bank"), "HDFCBANK.NS")

    def test_unknown_us_symbol_is_preserved(self):
        self.assertEqual(normalize_symbol("AAPL"), "AAPL")


if __name__ == "__main__":
    unittest.main()
