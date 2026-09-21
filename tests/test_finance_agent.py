import json
import unittest
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from finance_agent.mcp_client import PERSONAL_FINANCE_TOOL_NAMES
from finance_agent.runner import FinanceAgentRunner


class AccountBalanceArgs(BaseModel):
    account_type: str


class TransactionHistoryArgs(BaseModel):
    account_type: str
    n: int


class ExpenseBreakdownArgs(BaseModel):
    period: str


class StockQuoteArgs(BaseModel):
    ticker: str


class ScriptedChatModel(BaseChatModel):
    """Deterministic chat model that emits scripted tool calls, then a final answer."""

    responses: list[AIMessage]
    seen_messages: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-finance-agent"

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: str | None = None, **kwargs: Any):
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen_messages.append(list(messages))
        index = len(self.seen_messages) - 1
        if index >= len(self.responses):
            raise RuntimeError("Scripted chat model has no remaining responses.")
        return ChatResult(
            generations=[ChatGeneration(message=self.responses[index])]
        )


class RecordingMCPClient:
    def __init__(self, tools: list[StructuredTool]) -> None:
        self._tools = tools
        self.connect_calls = 0
        self.discover_calls = 0
        self.close_calls = 0

    async def connect(self) -> None:
        self.connect_calls += 1

    async def discover_tools(self) -> list[StructuredTool]:
        self.discover_calls += 1
        return self._tools

    async def aclose(self) -> None:
        self.close_calls += 1


def _mock_finance_tools(calls: list[tuple[str, dict[str, Any]]]) -> list[StructuredTool]:
    async def get_account_balance(account_type: str) -> str:
        payload = {
            "account_type": account_type,
            "balance": 2486.75,
            "currency": "USD",
        }
        calls.append(("get_account_balance", {"account_type": account_type}))
        return json.dumps(payload)

    async def get_transaction_history(account_type: str, n: int) -> str:
        payload = {"account_type": account_type, "transactions": []}
        calls.append(("get_transaction_history", {"account_type": account_type, "n": n}))
        return json.dumps(payload)

    async def get_portfolio_summary() -> str:
        payload = {"holdings": [], "total_market_value": 0}
        calls.append(("get_portfolio_summary", {}))
        return json.dumps(payload)

    async def get_expense_breakdown(period: str) -> str:
        payload = {
            "period": period,
            "total_expenses": 412.50,
            "categories": [{"category": "Groceries", "amount": 120.0}],
        }
        calls.append(("get_expense_breakdown", {"period": period}))
        return json.dumps(payload)

    async def get_stock_quote(ticker: str) -> str:
        payload = {
            "ticker": ticker.upper(),
            "latest_price": 226.25,
            "currency": "USD",
        }
        calls.append(("get_stock_quote", {"ticker": ticker}))
        return json.dumps(payload)

    return [
        StructuredTool.from_function(
            coroutine=get_account_balance,
            name="get_account_balance",
            description="Return the current balance for checking, savings, or credit_card.",
            args_schema=AccountBalanceArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_transaction_history,
            name="get_transaction_history",
            description="Return recent transactions for an account type.",
            args_schema=TransactionHistoryArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_portfolio_summary,
            name="get_portfolio_summary",
            description="Return holdings and total market value.",
        ),
        StructuredTool.from_function(
            coroutine=get_expense_breakdown,
            name="get_expense_breakdown",
            description="Return expenses by category for a period.",
            args_schema=ExpenseBreakdownArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_stock_quote,
            name="get_stock_quote",
            description="Return a USD market quote for a stock ticker.",
            args_schema=StockQuoteArgs,
        ),
    ]


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


class FinanceAgentRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.tools = _mock_finance_tools(self.calls)
        self.mcp_client = RecordingMCPClient(self.tools)

    async def _run(
        self,
        user_text: str,
        responses: list[AIMessage],
    ) -> str:
        model = ScriptedChatModel(responses=responses)
        runner = FinanceAgentRunner(chat_model=model, mcp_client=self.mcp_client)
        try:
            answer = await runner.ainvoke([{"role": "user", "content": user_text}])
            self.assertEqual({tool.name for tool in runner.tools}, PERSONAL_FINANCE_TOOL_NAMES)
        finally:
            await runner.stop()
        self.assertEqual(self.mcp_client.connect_calls, 1)
        self.assertEqual(self.mcp_client.discover_calls, 1)
        return answer

    async def test_balance_question_calls_get_account_balance(self) -> None:
        answer = await self._run(
            "What is my checking balance?",
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call("get_account_balance", {"account_type": "checking"}, "bal-1")
                    ],
                ),
                AIMessage(content="Your checking balance is $2,486.75."),
            ],
        )

        self.assertEqual(self.calls, [("get_account_balance", {"account_type": "checking"})])
        self.assertEqual(answer, "Your checking balance is $2,486.75.")

    async def test_spending_question_calls_get_expense_breakdown(self) -> None:
        answer = await self._run(
            "How much did I spend this month?",
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call("get_expense_breakdown", {"period": "this_month"}, "exp-1")
                    ],
                ),
                AIMessage(content="You spent $412.50 this month, including groceries."),
            ],
        )

        self.assertEqual(self.calls, [("get_expense_breakdown", {"period": "this_month"})])
        self.assertIn("412.50", answer)

    async def test_stock_question_calls_get_stock_quote(self) -> None:
        answer = await self._run(
            "What is Apple trading at?",
            [
                AIMessage(
                    content="",
                    tool_calls=[_tool_call("get_stock_quote", {"ticker": "AAPL"}, "q-1")],
                ),
                AIMessage(content="AAPL is at $226.25."),
            ],
        )

        self.assertEqual(self.calls, [("get_stock_quote", {"ticker": "AAPL"})])
        self.assertEqual(answer, "AAPL is at $226.25.")

    async def test_complex_question_calls_multiple_mcp_tools(self) -> None:
        answer = await self._run(
            "Compare my checking balance, this month's spending, and Apple's stock price.",
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call("get_account_balance", {"account_type": "checking"}, "m-1"),
                        _tool_call("get_expense_breakdown", {"period": "this_month"}, "m-2"),
                        _tool_call("get_stock_quote", {"ticker": "AAPL"}, "m-3"),
                    ],
                ),
                AIMessage(
                    content=(
                        "Checking is $2,486.75, this month's spending is $412.50, "
                        "and AAPL is $226.25."
                    )
                ),
            ],
        )

        called = {name for name, _ in self.calls}
        self.assertEqual(
            called,
            {"get_account_balance", "get_expense_breakdown", "get_stock_quote"},
        )
        self.assertIn("2,486.75", answer)
        self.assertIn("412.50", answer)
        self.assertIn("226.25", answer)

    async def test_discovers_exactly_the_five_mcp_tools(self) -> None:
        runner = FinanceAgentRunner(
            chat_model=ScriptedChatModel(responses=[AIMessage(content="ok")]),
            mcp_client=self.mcp_client,
        )
        await runner.start()
        try:
            self.assertEqual(
                {tool.name for tool in runner.tools},
                PERSONAL_FINANCE_TOOL_NAMES,
            )
        finally:
            await runner.stop()


if __name__ == "__main__":
    unittest.main()
