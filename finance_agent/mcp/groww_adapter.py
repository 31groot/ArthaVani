"""Read-only wrapper around Groww's official ``growwapi`` SDK."""
from __future__ import annotations

from contextlib import redirect_stdout
import sys
from typing import Any, Callable, Protocol

from config.settings import settings


class GrowwSDK(Protocol):
    def get_user_profile(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_holdings_for_user(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_positions_for_user(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_position_for_trading_symbol(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_quote(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_ltp(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_historical_candle_data(self, **kwargs: Any) -> dict[str, Any]: ...


class GrowwAuthenticationError(RuntimeError):
    """Raised without echoing sensitive credential values."""


class GrowwAdapter:
    """Small, explicit read-only interface over the official Groww SDK."""

    def __init__(self, sdk: GrowwSDK) -> None:
        self._sdk = sdk

    @classmethod
    def from_environment(cls) -> "GrowwAdapter":
        """Create the official SDK from non-repository environment settings.

        """
        try:
            from growwapi import GrowwAPI
        except ImportError as error:
            raise GrowwAuthenticationError(
                "growwapi is not installed; install project dependencies first."
            ) from error
        

        api_key = settings.GROWW_API_KEY
        api_secret = settings.GROWW_API_SECRET
        if not api_key or not api_secret:
            raise GrowwAuthenticationError(
                "Set GROWW_API_KEY and GROWW_API_SECRET."
            )
        try:
            # growwapi currently prints a banner/changelog during initialization.
            # The local MCP process reserves stdout for JSON-RPC, so contain SDK
            # console output at this boundary and send it to stderr instead.
            with redirect_stdout(sys.stderr):
                token = GrowwAPI.get_access_token(api_key=api_key, secret=api_secret)
                sdk = GrowwAPI(token)
        except Exception as error:
            raise GrowwAuthenticationError("Groww SDK authentication failed.") from error
        return cls(sdk)

    def _call(self, method: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Prevent any SDK diagnostic prints from corrupting MCP stdout."""
        with redirect_stdout(sys.stderr):
            return method(**kwargs)

    def get_user_profile(self) -> dict[str, Any]:
        return self._call(self._sdk.get_user_profile)

    def get_holdings(self) -> dict[str, Any]:
        return self._call(self._sdk.get_holdings_for_user)

    def get_positions(self, segment: str | None = None) -> dict[str, Any]:
        kwargs = {"segment": segment} if segment else {}
        return self._call(self._sdk.get_positions_for_user, **kwargs)

    def get_position(self, trading_symbol: str, segment: str) -> dict[str, Any]:
        return self._call(
            self._sdk.get_position_for_trading_symbol,
            trading_symbol=trading_symbol, segment=segment,
        )

    def get_quote(self, exchange: str, segment: str, trading_symbol: str) -> dict[str, Any]:
        return self._call(
            self._sdk.get_quote,
            exchange=exchange, segment=segment, trading_symbol=trading_symbol,
        )

    def get_ltp(self, segment: str, exchange_trading_symbols: list[str]) -> dict[str, Any]:
        return self._call(
            self._sdk.get_ltp,
            segment=segment, exchange_trading_symbols=tuple(exchange_trading_symbols),
        )

    def get_historical_data(
        self, exchange: str, segment: str, trading_symbol: str,
        start_time: str, end_time: str, interval_in_minutes: int | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "exchange": exchange, "segment": segment,
            "trading_symbol": trading_symbol, "start_time": start_time,
            "end_time": end_time,
        }
        if interval_in_minutes is not None:
            kwargs["interval_in_minutes"] = interval_in_minutes
        return self._call(self._sdk.get_historical_candle_data, **kwargs)
