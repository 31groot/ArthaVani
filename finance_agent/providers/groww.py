"""User-scoped, read-only Groww provider for ArthaVani."""
from __future__ import annotations

import os
from contextlib import redirect_stdout
from decimal import Decimal
from functools import lru_cache
from typing import Any

from config.settings import settings
from finance_agent.groww_credentials import decrypt_credentials
from finance_agent.persistence import get_groww_connection
from finance_agent.user_context import get_current_user_id


class GrowwProvider:
    """Reusable wrapper around the official Groww Python SDK."""

    def __init__(
        self,
        *,
        auth_mode: str | None = None,
        credentials: dict[str, str] | None = None,
    ) -> None:
        try:
            from growwapi import GrowwAPI
        except ImportError as exc:
            raise RuntimeError(
                "growwapi is not installed. Install project dependencies first."
            ) from exc

        self._GrowwAPI = GrowwAPI
        self.auth_mode = auth_mode
        self.credentials = credentials or {}

        if auth_mode is None:
            api_key = settings.GROWW_API_KEY
            api_secret = settings.GROWW_API_SECRET
            if not api_key or not api_secret:
                raise RuntimeError(
                    "GROWW_API_KEY and GROWW_API_SECRET are required."
                )
            self.auth_mode = "api_key_secret"
            self.credentials = {
                "api_key": api_key,
                "api_secret": api_secret,
            }

        self.client = self._authenticate()

    def _authenticate(self):
        with open(os.devnull, "w") as _groww_stdout, redirect_stdout(_groww_stdout):
            if self.auth_mode == "api_key_secret":
                access_token = self._GrowwAPI.get_access_token(
                    api_key=self.credentials["api_key"],
                    secret=self.credentials["api_secret"],
                )
            elif self.auth_mode == "totp":
                try:
                    import pyotp
                except ImportError as exc:
                    raise RuntimeError(
                        "pyotp is required for Groww TOTP connections."
                    ) from exc

                otp = pyotp.TOTP(self.credentials["totp_secret"]).now()
                access_token = self._GrowwAPI.get_access_token(
                    api_key=self.credentials["totp_token"],
                    totp=otp,
                )
            else:
                raise RuntimeError(f"Unsupported Groww auth mode: {self.auth_mode!r}")

            return self._GrowwAPI(access_token)

    def _call(self, method_name: str, **kwargs: Any) -> Any:
        try:
            with open(
                os.devnull,
                "w",
            ) as _groww_stdout, redirect_stdout(_groww_stdout):
                return getattr(self.client, method_name)(**kwargs)
        except Exception:
            # The provider only exposes read-only operations here, so it is
            # safe to refresh the Groww session once before retrying.
            self.client = self._authenticate()
            with open(
                os.devnull,
                "w",
            ) as _groww_stdout, redirect_stdout(_groww_stdout):
                return getattr(self.client, method_name)(**kwargs)

    def get_holdings(self) -> dict[str, Any]:
        return self._call("get_holdings_for_user")

    def get_positions(self, segment: str | None = None) -> dict[str, Any]:
        if segment:
            return self._call(
                "get_positions_for_user",
                segment=segment,
            )
        return self._call("get_positions_for_user")

    def get_quote(
        self,
        exchange: str,
        segment: str,
        trading_symbol: str,
    ) -> dict[str, Any]:
        return self._call(
            "get_quote",
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
            "get_ltp",
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

        return self._call(
            "get_historical_candle_data",
            **kwargs,
        )


def build_groww_provider_from_credentials(
    auth_mode: str,
    credentials: dict[str, str],
) -> GrowwProvider:
    return GrowwProvider(
        auth_mode=auth_mode,
        credentials=credentials,
    )


@lru_cache(maxsize=1)
def _legacy_groww_provider() -> GrowwProvider:
    return GrowwProvider()


@lru_cache(maxsize=64)
def _user_groww_provider(
    user_id: str,
    updated_at: str,
    auth_mode: str,
    encrypted_credentials: str,
) -> GrowwProvider:
    del updated_at
    credentials = decrypt_credentials(encrypted_credentials)
    return GrowwProvider(
        auth_mode=auth_mode,
        credentials=credentials,
    )


def get_groww_provider() -> GrowwProvider:
    """Return the provider for the authenticated user or local env fallback."""
    user_id = get_current_user_id()

    if not user_id:
        return _legacy_groww_provider()

    connection = get_groww_connection(user_id)
    if connection is None:
        raise RuntimeError(
            "Groww is not connected for this user. Connect Groww first."
        )

    updated_at = str(connection["updated_at"])
    return _user_groww_provider(
        user_id,
        updated_at,
        connection["auth_mode"],
        connection["encrypted_credentials"],
    )


def holding_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
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
