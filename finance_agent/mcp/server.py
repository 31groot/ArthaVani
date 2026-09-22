"""Local, read-only MCP server backed by the official Groww Python SDK."""
from __future__ import annotations

from typing import Any
from mcp.server.fastmcp import FastMCP
from finance_agent.mcp.groww_adapter import GrowwAdapter


def create_server(adapter: GrowwAdapter | None = None) -> FastMCP:
    adapter = adapter or GrowwAdapter.from_environment()
    server = FastMCP("ArthaVani Groww Read-Only MCP")

    @server.tool()
    def get_user_profile() -> dict[str, Any]:
        """Return the authenticated Groww user's profile."""
        return adapter.get_user_profile()

    @server.tool()
    def get_holdings() -> dict[str, Any]:
        """Return current demat holdings and quantities."""
        return adapter.get_holdings()

    @server.tool()
    def get_positions(segment: str | None = None) -> dict[str, Any]:
        """Return current CASH and/or FNO positions; optional segment is CASH or FNO."""
        return adapter.get_positions(segment)

    @server.tool()
    def get_position(trading_symbol: str, segment: str) -> dict[str, Any]:
        """Return a position for a trading symbol in CASH or FNO."""
        return adapter.get_position(trading_symbol, segment)

    @server.tool()
    def get_quote(exchange: str, segment: str, trading_symbol: str) -> dict[str, Any]:
        """Return a real-time quote for one instrument."""
        return adapter.get_quote(exchange, segment, trading_symbol)

    @server.tool()
    def get_ltp(segment: str, exchange_trading_symbols: list[str]) -> dict[str, Any]:
        """Return last traded prices for up to 50 EXCHANGE_SYMBOL values."""
        return adapter.get_ltp(segment, exchange_trading_symbols)

    @server.tool()
    def get_historical_data(
        exchange: str, segment: str, trading_symbol: str, start_time: str,
        end_time: str, interval_in_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Return historical OHLCV candles for one instrument and time range."""
        return adapter.get_historical_data(
            exchange, segment, trading_symbol, start_time, end_time, interval_in_minutes
        )

    return server


if __name__ == "__main__":
    create_server().run(transport="stdio")
