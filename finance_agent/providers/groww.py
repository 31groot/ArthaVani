"""Direct, read-only Groww provider for native LangGraph tools."""
from __future__ import annotations

import os
from contextlib import redirect_stdout
from decimal import Decimal
from functools import lru_cache
from typing import Any

from config.settings import settings


class GrowwProvider:
    """Small reusable wrapper around the official Groww Python SDK."""

    def __init__(self) -> None:
        try:
            from growwapi import GrowwAPI
        except ImportError as exc:
            raise RuntimeError(
                "growwapi is not installed. Install project dependencies first."
            ) from exc

        api_key = settings.GROWW_API_KEY
        api_secret = settings.GROWW_API_SECRET
        if not api_key or not api_secret:
            raise RuntimeError(
                "GROWW_API_KEY and GROWW_API_SECRET are required."
            )

        # The SDK currently prints a startup banner. Keep it out of the voice
        # application's normal stdout stream.
        with open(os.devnull, "w") as _groww_stdout, redirect_stdout(_groww_stdout):
            access_token = GrowwAPI.get_access_token(
                api_key=api_key,
                secret=api_secret,
            )
            self.client = GrowwAPI(access_token)

    def _call(self, method, **kwargs: Any) -> Any:
        with open(os.devnull, "w") as _groww_stdout, redirect_stdout(_groww_stdout):
            return method(**kwargs)

    def get_holdings(self) -> dict[str, Any]:
        return self._call(self.client.get_holdings_for_user)

    def get_positions(self, segment: str | None = None) -> dict[str, Any]:
        if segment:
            return self._call(
                self.client.get_positions_for_user,
                segment=segment,
            )
        return self._call(self.client.get_positions_for_user)

    def get_quote(
        self,
        exchange: str,
        segment: str,
        trading_symbol: str,
    ) -> dict[str, Any]:
        return self._call(
            self.client.get_quote,
            exchange=exchange,
            segment=segment,
            trading_symbol=trading_symbol,
        )

    def get_ltp(
        self,
        segment: str,
        exchange_trading_symbols: list[str],
    ) -> dict[str, Any]:
        return self._call(
            self.client.get_ltp,
            segment=segment,
            exchange_trading_symbols=tuple(exchange_trading_symbols),
        )

    def get_historical_data(
        self,
        exchange: str,
        segment: str,
        trading_symbol: str,
        start_time: str,
        end_time: str,
        interval_in_minutes: int | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "exchange": exchange,
            "segment": segment,
            "trading_symbol": trading_symbol,
            "start_time": start_time,
            "end_time": end_time,
        }
        if interval_in_minutes is not None:
            kwargs["interval_in_minutes"] = interval_in_minutes

        # Groww currently documents this endpoint, although it marks the
        # method as deprecated in favor of get_historical_candles.
        return self._call(
            self.client.get_historical_candle_data,
            **kwargs,
        )


@lru_cache(maxsize=1)
def get_groww_provider() -> GrowwProvider:
    """Reuse one authenticated Groww SDK client within the process."""
    return GrowwProvider()


def holding_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the holdings response into a list of dictionaries."""
    if not isinstance(payload, dict):
        return []

    rows = payload.get("holdings")
    if rows is None and isinstance(payload.get("payload"), dict):
        rows = payload["payload"].get("holdings")

    if not isinstance(rows, list):
        return []

    return [row for row in rows if isinstance(row, dict)]


def decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def preferred_exchange(row: dict[str, Any]) -> str:
    exchanges = row.get("tradable_exchanges") or []
    if "NSE" in exchanges:
        return "NSE"
    if "BSE" in exchanges:
        return "BSE"
    if exchanges:
        return str(exchanges[0])
    return "NSE"
