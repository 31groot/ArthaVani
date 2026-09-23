import unittest

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from finance_agent.runner import FinanceAgentRunner


class FakeChatModel:
    """Minimal async model used to exercise LangGraph tool routing."""

    def __init__(self):
        self.bound_tools = {}
        self.tool_calls = []

    def bind_tools(self, tools):
        self.bound_tools = {item.name: item for item in tools}
        return self

    async def ainvoke(self, messages, config=None, **kwargs):
        last = messages[-1]

        if isinstance(last, ToolMessage):
            return AIMessage(
                content=f"Tool result received from {last.name}."
            )

        user_text = str(last.content).lower()

        if "portfolio" in user_text and ("p&l" in user_text or "pnl" in user_text):
            name = "get_portfolio_summary"
            args = {}
        elif "concentrated" in user_text or "concentration" in user_text:
            name = "get_portfolio_risk"
            args = {}
        elif "infosys" in user_text or "price" in user_text:
            name = "yahoo_get_quote"
            args = {"ticker": "INFY.NS"}
        elif "convert" in user_text or "dollars" in user_text or "usd" in user_text:
            name = "convert_currency"
            args = {
                "amount": 100.0,
                "from_currency": "USD",
                "to_currency": "INR",
            }
        else:
            return AIMessage(content="No tool selected.")

        self.tool_calls.append(name)
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": name,
                    "args": args,
                    "id": f"call_{len(self.tool_calls)}",
                    "type": "tool_call",
                }
            ],
        )


class AgentRoutingTests(unittest.IsolatedAsyncioTestCase):

    def _runner(self, model):
        @tool
        def get_portfolio_summary() -> dict:
            """Return a fake portfolio summary."""
            return {
                "market_data_available": True,
                "market_data_realtime": False,
                "profit_loss": -3314.1,
            }

        @tool
        def get_portfolio_risk() -> dict:
            """Return fake portfolio concentration."""
            return {"concentration_hhi": 0.6756}

        @tool
        def yahoo_get_quote(ticker: str) -> dict:
            """Return a fake Yahoo quote."""
            return {"ticker": ticker, "latest_price": 1038.5}

        @tool
        def convert_currency(
            amount: float,
            from_currency: str,
            to_currency: str,
        ) -> dict:
            """Return a fake FX conversion."""
            return {
                "amount": amount,
                "from_currency": from_currency,
                "to_currency": to_currency,
                "converted_amount": 8300.0,
            }

        return FinanceAgentRunner(
            chat_model=model,
            tools=[
                get_portfolio_summary,
                get_portfolio_risk,
                yahoo_get_quote,
                convert_currency,
            ],
        )

    async def test_portfolio_routes_to_summary(self):
        model = FakeChatModel()
        runner = self._runner(model)
        result = await runner.ainvoke(
            [{"role": "user", "content": "What's my portfolio P&L?"}]
        )
        self.assertEqual(model.tool_calls, ["get_portfolio_summary"])
        self.assertIn("Tool result received", result)

    async def test_portfolio_risk_routes_to_risk_tool(self):
        model = FakeChatModel()
        runner = self._runner(model)
        result = await runner.ainvoke(
            [{"role": "user", "content": "How concentrated is my portfolio?"}]
        )
        self.assertEqual(model.tool_calls, ["get_portfolio_risk"])
        self.assertIn("Tool result received", result)

    async def test_stock_price_routes_to_yahoo(self):
        model = FakeChatModel()
        runner = self._runner(model)
        result = await runner.ainvoke(
            [{"role": "user", "content": "What's the price of Infosys?"}]
        )
        self.assertEqual(model.tool_calls, ["yahoo_get_quote"])
        self.assertIn("Tool result received", result)

    async def test_fx_routes_to_converter(self):
        model = FakeChatModel()
        runner = self._runner(model)
        result = await runner.ainvoke(
            [{"role": "user", "content": "Convert 100 USD to INR."}]
        )
        self.assertEqual(model.tool_calls, ["convert_currency"])
        self.assertIn("Tool result received", result)


if __name__ == "__main__":
    unittest.main()
