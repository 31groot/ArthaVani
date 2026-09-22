import unittest
from finance_agent.mcp.groww_adapter import GrowwAdapter

class FakeSDK:
    def get_user_profile(self): return {"name": "Test User"}
    def get_holdings_for_user(self): return {"holdings": []}
    def get_positions_for_user(self, **kwargs): return {"positions": [], **kwargs}
    def get_position_for_trading_symbol(self, **kwargs): return {"positions": [kwargs]}
    def get_quote(self, **kwargs): return {"last_price": 100, **kwargs}
    def get_ltp(self, **kwargs): return {"NSE_TEST": 100, **kwargs}
    def get_historical_candle_data(self, **kwargs): return {"candles": [], **kwargs}

class GrowwAdapterTests(unittest.TestCase):
    def setUp(self): self.adapter = GrowwAdapter(FakeSDK())
    def test_read_only_adapter_methods(self):
        self.assertEqual(self.adapter.get_user_profile()["name"], "Test User")
        self.assertEqual(self.adapter.get_holdings(), {"holdings": []})
        self.assertEqual(self.adapter.get_positions("CASH")["segment"], "CASH")
        self.assertEqual(self.adapter.get_quote("NSE", "CASH", "TEST")["trading_symbol"], "TEST")
        self.assertEqual(self.adapter.get_ltp("CASH", ["NSE_TEST"])["NSE_TEST"], 100)
    def test_only_read_operations_are_exposed(self):
        self.assertFalse(hasattr(self.adapter, "place_order"))
        self.assertFalse(hasattr(self.adapter, "cancel_order"))

if __name__ == "__main__": unittest.main()
