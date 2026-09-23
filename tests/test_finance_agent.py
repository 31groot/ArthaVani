import json
import unittest
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from finance_agent.runner import FinanceAgentRunner


class AccountArgs(BaseModel):
    account_type: str


class PeriodArgs(BaseModel):
    period: str


class StockQuoteArgs(BaseModel):
    ticker: str


class ScriptedChatModel(BaseChatModel):
    """Deterministic model used to test LangGraph tool execution."""

    responses: list[AIMessage]
    seen_messages: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-finance-agent"

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ):
        # The test model already returns scripted tool calls.
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


def _tool_call(
    name: str,
    args: dict[str, Any],
    call_id: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "args": args,
        "id": call_id,
        "type": "tool_call",
    }


def _mock_tools(calls: list[tuple[str, dict[str, Any]]]) -> list[StructuredTool]:
    async def get_account_balance(account_type: str) -> str:
        calls.append(("get_account_balance", {"account_type": account_type}))
        return json.dumps({
            "account_type": account_type,
            "balance": 2486.75,
            "currency": "USD",
        })

    async def get_expense_breakdown(period: str) -> str:
        calls.append(("get_expense_breakdown", {"period": period}))
        return json.dumps({
            "period": period,
            "total_expenses": 412.50,
        })

    async def get_stock_quote(ticker: str) -> str:
        calls.append(("get_stock_quote", {"ticker": ticker}))
        return json.dumps({
            "ticker": ticker.upper(),
            "latest_price": 226.25,
            "currency": "USD",
        })

    return [
        StructuredTool.from_function(
            coroutine=get_account_balance,
            name="get_account_balance",
            description="Return a balance.",
            args_schema=AccountArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_expense_breakdown,
            name="get_expense_breakdown",
            description="Return spending.",
            args_schema=PeriodArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_stock_quote,
            name="get_stock_quote",
            description="Return a stock quote.",
            args_schema=StockQuoteArgs,
        ),
    ]


class FinanceAgentRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_injected_tools_are_used_directly(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []
        tools = _mock_tools(calls)

        model = ScriptedChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "get_account_balance",
                            {"account_type": "checking"},
                            "bal-1",
                        )
                    ],
                ),
                AIMessage(content="Your checking balance is $2,486.75."),
            ]
        )

        runner = FinanceAgentRunner(
            chat_model=model,
            tools=tools,
        )

        answer = await runner.ainvoke([
            {"role": "user", "content": "What is my checking balance?"}
        ])

        self.assertEqual(answer, "Your checking balance is $2,486.75.")
        self.assertEqual(
            calls,
            [("get_account_balance", {"account_type": "checking"})],
        )
        self.assertEqual(
            {tool.name for tool in runner.tools},
            {
                "get_account_balance",
                "get_expense_breakdown",
                "get_stock_quote",
            },
        )

        await runner.stop()

    async def test_multiple_native_tools_can_be_called_in_one_turn(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []
        tools = _mock_tools(calls)

        model = ScriptedChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "get_account_balance",
                            {"account_type": "checking"},
                            "m-1",
                        ),
                        _tool_call(
                            "get_expense_breakdown",
                            {"period": "this_month"},
                            "m-2",
                        ),
                        _tool_call(
                            "get_stock_quote",
                            {"ticker": "AAPL"},
                            "m-3",
                        ),
                    ],
                ),
                AIMessage(
                    content=(
                        "Checking is $2,486.75, spending is $412.50, "
                        "and AAPL is $226.25."
                    )
                ),
            ]
        )

        runner = FinanceAgentRunner(chat_model=model, tools=tools)

        answer = await runner.ainvoke([
            {"role": "user", "content": "Give me a combined finance summary."}
        ])

        self.assertEqual(
            {name for name, _ in calls},
            {
                "get_account_balance",
                "get_expense_breakdown",
                "get_stock_quote",
            },
        )
        self.assertIn("2,486.75", answer)
        self.assertIn("412.50", answer)
        self.assertIn("226.25", answer)

        await runner.stop()

    async def test_start_is_idempotent(self) -> None:
        tools = _mock_tools([])
        model = ScriptedChatModel(responses=[AIMessage(content="ok")])

        runner = FinanceAgentRunner(chat_model=model, tools=tools)

        await runner.start()
        first_graph = runner._graph

        await runner.start()

        self.assertIs(runner._graph, first_graph)
        self.assertIsNotNone(runner.tools)

        await runner.stop()
        self.assertIsNone(runner._graph)
        self.assertIsNone(runner._tools)

    async def test_streams_model_text_only(self) -> None:
        tools = _mock_tools([])
        model = ScriptedChatModel(
            responses=[
                AIMessage(content="Hello from the finance agent."),
            ]
        )

        runner = FinanceAgentRunner(chat_model=model, tools=tools)

        chunks = []
        async for chunk in runner.astream_text([
            {"role": "user", "content": "Hello"}
        ]):
            chunks.append(chunk)

        self.assertTrue(chunks)
        self.assertEqual("".join(chunks), "Hello from the finance agent.")

        await runner.stop()


if __name__ == "__main__":
    unittest.main()
