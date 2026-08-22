import asyncio
import json
from typing import Any

import mcp_types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from personal_finance_mcp.database import DEFAULT_DATABASE_PATH, seed_database
from personal_finance_mcp.service import PersonalFinanceService


# Bootstrap is the only database-writing operation and occurs before serving.
# Every MCP request opens SQLite with mode=ro and PRAGMA query_only enabled.
seed_database(DEFAULT_DATABASE_PATH)
service = PersonalFinanceService()

TOOLS = [
    types.Tool(
        name="get_account_balance",
        description="Return the current balance for checking, savings, or credit_card.",
        inputSchema={"type": "object", "properties": {"account_type": {"type": "string"}}, "required": ["account_type"], "additionalProperties": False},
    ),
    types.Tool(
        name="get_transaction_history",
        description="Return up to 50 recent transactions for a supported account type.",
        inputSchema={"type": "object", "properties": {"account_type": {"type": "string"}, "n": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["account_type", "n"], "additionalProperties": False},
    ),
    types.Tool(
        name="get_portfolio_summary",
        description="Return holdings, total market value, and unrealized gains.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="get_expense_breakdown",
        description="Return expenses by category for this_month, last_month, last_30_days, or year_to_date.",
        inputSchema={"type": "object", "properties": {"period": {"type": "string"}}, "required": ["period"], "additionalProperties": False},
    ),
    types.Tool(
        name="get_stock_quote",
        description="Return a mock USD market quote for a supported stock ticker.",
        inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"], "additionalProperties": False},
    ),
]


def get_account_balance(account_type: str) -> dict[str, object]:
    return service.get_account_balance(account_type)


def get_transaction_history(account_type: str, n: int) -> dict[str, object]:
    return service.get_transaction_history(account_type, n)


def get_portfolio_summary() -> dict[str, object]:
    return service.get_portfolio_summary()


def get_expense_breakdown(period: str) -> dict[str, object]:
    return service.get_expense_breakdown(period)


def get_stock_quote(ticker: str) -> dict[str, object]:
    return service.get_stock_quote(ticker)


TOOL_HANDLERS = {
    "get_account_balance": lambda arguments: get_account_balance(arguments["account_type"]),
    "get_transaction_history": lambda arguments: get_transaction_history(arguments["account_type"], arguments["n"]),
    "get_portfolio_summary": lambda arguments: get_portfolio_summary(),
    "get_expense_breakdown": lambda arguments: get_expense_breakdown(arguments["period"]),
    "get_stock_quote": lambda arguments: get_stock_quote(arguments["ticker"]),
}
TOOL_ARGUMENTS = {
    "get_account_balance": {"account_type"},
    "get_transaction_history": {"account_type", "n"},
    "get_portfolio_summary": set(),
    "get_expense_breakdown": {"period"},
    "get_stock_quote": {"ticker"},
}


async def list_tools(_: Any, __: Any) -> types.ListToolsResult:
    return types.ListToolsResult(tools=TOOLS)


async def call_tool(_: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
    handler = TOOL_HANDLERS.get(params.name)
    if handler is None:
        return _error_result(f"Unknown tool '{params.name}'.")
    arguments = params.arguments or {}
    unexpected = set(arguments) - TOOL_ARGUMENTS[params.name]
    if unexpected:
        return _error_result(f"Unexpected argument(s): {', '.join(sorted(unexpected))}.")
    try:
        result = handler(arguments)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        return _error_result(str(error))
    return types.CallToolResult(
        content=[types.TextContent(text=json.dumps(result, separators=(",", ":")))],
        structuredContent=result,
    )


def _error_result(message: str) -> types.CallToolResult:
    error = {"error": message}
    return types.CallToolResult(
        content=[types.TextContent(text=json.dumps(error, separators=(",", ":")))],
        structuredContent=error,
        isError=True,
    )


mcp = Server(
    "PersonalFinance",
    version="0.1.0",
    instructions="Read-only personal-finance demo data.",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)


async def run_stdio() -> None:
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


def main() -> None:
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
