from datetime import datetime, timezone
from typing import Any

import yfinance as yf


class YahooFinanceQuoteProvider:

    def get_quote(self, ticker: str) -> dict[str, object]:
        symbol = self._normalize_ticker(ticker)
        try:
            instrument = yf.Ticker(symbol)
            history = instrument.history(
                period="5d",
                interval="1d",
                auto_adjust=False,
                raise_errors=True,
            )
            if history is None or history.empty or "Close" not in history:
                raise ValueError(
                    f"No Yahoo Finance price data is available for '{symbol}'."
                )
            
            closes = history["Close"].dropna()
            if closes.empty:
                raise ValueError(
                    f"No usable Yahoo Finance close price is available for '{symbol}'."
                )

            latest_price = float(closes.iloc[-1])
            previous_close = float(closes.iloc[-2]) if len(closes) > 1 else latest_price
            metadata = instrument.get_history_metadata() or {}
            info = instrument.get_info() or {}
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(self._provider_error(symbol, error)) from error

        company_name = (
            info.get("longName")
            or info.get("shortName")
            or metadata.get("longName")
            or metadata.get("shortName")
            or symbol
        )
        currency = info.get("currency") or metadata.get("currency")
        if not currency:
            raise ValueError(f"Yahoo Finance did not return a currency for '{symbol}'.")

        timestamp = self._timestamp(metadata, closes.index[-1])
        change = latest_price - previous_close
        return {
            "ticker": symbol,
            "company_name": company_name,
            "latest_price": round(latest_price, 4),
            "previous_close": round(previous_close, 4),
            "currency": currency,
            "change": round(change, 4),
            "change_percentage": round((change / previous_close) * 100, 4) if previous_close else None,
            "data_timestamp": timestamp,
        }

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        if not isinstance(ticker, str):
            raise ValueError("ticker must be a string")
        symbol = ticker.strip().upper()
        if not symbol or len(symbol) > 20 or not all(character.isalnum() or character in ".-^=" for character in symbol):
            raise ValueError("ticker must be a valid Yahoo Finance symbol, for example AAPL or RELIANCE.NS")
        return symbol

    @staticmethod
    def _timestamp(metadata: dict[str, Any], latest_index: Any) -> str:
        market_time = metadata.get("regularMarketTime")
        if isinstance(market_time, (int, float)):
            return datetime.fromtimestamp(market_time, tz=timezone.utc).isoformat()
        if hasattr(latest_index, "isoformat"):
            return latest_index.isoformat()
        return str(latest_index)

    @staticmethod
    def _provider_error(symbol: str, error: Exception) -> str:
        message = str(error).strip()
        if "429" in message or "rate limit" in message.lower():
            return f"Yahoo Finance rate limited quote requests for '{symbol}'. Please try again shortly."
        if "not found" in message.lower() or "delisted" in message.lower():
            return f"Yahoo Finance could not find ticker '{symbol}'."
        return f"Yahoo Finance quote lookup failed for '{symbol}'. Please try again later."
