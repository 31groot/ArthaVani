"""Yahoo Finance provider and local technical-analysis helpers."""
from __future__ import annotations

from datetime import datetime
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import requests
import yfinance as yf

from config.logger import logger


# India-first aliases for common Indian equities.
INDIA_TICKER_ALIASES: dict[str, str] = {
    "INFOSYS": "INFY.NS",
    "INFY": "INFY.NS",
    "TCS": "TCS.NS",
    "TATA CONSULTANCY SERVICES": "TCS.NS",
    "RELIANCE": "RELIANCE.NS",
    "RELIANCE INDUSTRIES": "RELIANCE.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "HDFC BANK": "HDFCBANK.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "ICICI BANK": "ICICIBANK.NS",
    "SBIN": "SBIN.NS",
    "STATE BANK OF INDIA": "SBIN.NS",
    "ITC": "ITC.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "BHARTI AIRTEL": "BHARTIARTL.NS",
    "DATAPATTNS": "DATAPATTNS.NS",
    "BSE": "BSE.NS",
}


NEWS_CACHE_TTL_SECONDS = 60

_news_cache: dict[
    tuple[str, int],
    tuple[float, list[dict[str, Any]]],
] = {}

_news_cache_lock = Lock()


def normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if not cleaned:
        raise ValueError("ticker must not be empty")
    return INDIA_TICKER_ALIASES.get(cleaned, cleaned)


class YahooProvider:
    """Read-only market/company data provider backed by yfinance."""

    @staticmethod
    def ticker(symbol: str) -> yf.Ticker:
        return yf.Ticker(normalize_symbol(symbol))

    def quote(self, symbol: str) -> dict[str, Any]:
        ticker = self.ticker(symbol)
        history = ticker.history(
            period="5d",
            interval="1d",
            auto_adjust=False,
            raise_errors=True,
        )
        if history is None or history.empty or "Close" not in history:
            raise ValueError(f"No Yahoo Finance price data for '{symbol}'.")

        closes = history["Close"].dropna()
        if closes.empty:
            raise ValueError(f"No Yahoo Finance close price for '{symbol}'.")

        latest = float(closes.iloc[-1])
        previous = float(closes.iloc[-2]) if len(closes) > 1 else latest
        change = latest - previous
        metadata = ticker.get_history_metadata() or {}

        return {
            "ticker": normalize_symbol(symbol),
            "latest_price": round(latest, 4),
            "previous_close": round(previous, 4),
            "change": round(change, 4),
            "change_percentage": round((change / previous) * 100, 4)
            if previous
            else None,
            "currency": metadata.get("currency"),
            "data_timestamp": (
                datetime.fromtimestamp(
                    metadata["regularMarketTime"]
                ).isoformat()
                if isinstance(metadata.get("regularMarketTime"), (int, float))
                else str(closes.index[-1])
            ),
        }

    def fundamentals(self, symbol: str) -> dict[str, Any]:
        info = self.ticker(symbol).get_info() or {}
        fields = (
            "longName",
            "shortName",
            "sector",
            "industry",
            "marketCap",
            "trailingPE",
            "forwardPE",
            "priceToBook",
            "enterpriseToEbitda",
            "profitMargins",
            "returnOnEquity",
            "revenueGrowth",
            "earningsGrowth",
            "dividendYield",
        )
        result = {"ticker": symbol.strip().upper()}
        for field in fields:
            value = info.get(field)
            if value is not None:
                result[field] = value
        return result

    def history(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        history = self.ticker(symbol).history(
            period=period,
            interval=interval,
            auto_adjust=False,
        )
        if history is None or history.empty:
            return []

        rows: list[dict[str, Any]] = []
        for index, row in history.tail(250).iterrows():
            rows.append({
                "date": index.isoformat(),
                "open": _number(row.get("Open")),
                "high": _number(row.get("High")),
                "low": _number(row.get("Low")),
                "close": _number(row.get("Close")),
                "volume": _number(row.get("Volume")),
            })
        return rows

    def technical_analysis(
        self,
        symbol: str,
        period: str = "6mo",
    ) -> dict[str, Any]:
        history = self.ticker(symbol).history(
            period=period,
            interval="1d",
            auto_adjust=False,
        )
        if history is None or history.empty:
            raise ValueError(f"No price history available for '{symbol}'.")

        close = history["Close"].dropna()
        if close.empty:
            raise ValueError(f"No close prices available for '{symbol}'.")

        sma20 = close.rolling(20).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))

        latest = float(close.iloc[-1])
        return {
            "ticker": normalize_symbol(symbol),
            "latest_close": round(latest, 4),
            "sma20": _optional_number(sma20),
            "sma50": _optional_number(sma50),
            "rsi14": _optional_number(rsi.iloc[-1]),
            "trend_signal": _trend_signal(latest, sma20, sma50),
            "period": period,
        }

    def news(self, symbol: str, count: int = 5) -> list[dict[str, Any]]:
        normalized = normalize_symbol(symbol)
        count = max(1, min(count, 10))
        cache_key = (normalized, count)

        now = monotonic()

        with _news_cache_lock:
            cached = _news_cache.get(cache_key)

        if cached is not None:
            cached_at, cached_items = cached
            if now - cached_at < NEWS_CACHE_TTL_SECONDS:
                return list(cached_items)

        result: list[dict[str, Any]] = []

        # Primary provider: Yahoo Finance.
        try:
            items = (
                self.ticker(normalized).get_news(count=count)
                or []
            )

            for item in items:
                content = item.get("content", item)

                if not isinstance(content, dict):
                    continue

                title = content.get("title")

                if not title:
                    continue

                result.append({
                    "title": title,
                    "publisher": (
                        content.get("provider", {}) or {}
                    ).get("displayName")
                    if isinstance(content.get("provider"), dict)
                    else None,
                    "published": content.get("pubDate"),
                    "url": (
                        (content.get("canonicalUrl") or {}).get("url")
                        if isinstance(content.get("canonicalUrl"), dict)
                        else None
                    ),
                })

        except Exception:
            logger.exception(
                "Yahoo news fetch failed for %s. "
                "Trying RSS fallback.",
                normalized,
            )

        # Fallback provider: Google News RSS.
        if not result:
            result = _google_news_rss(normalized, count)

        with _news_cache_lock:
            _news_cache[cache_key] = (now, list(result))

        return result

    def corporate_actions(self, symbol: str, period: str = "1y") -> dict[str, Any]:
        ticker = self.ticker(symbol)
        dividends = ticker.get_dividends(period=period)
        splits = ticker.get_splits(period=period)

        return {
            "ticker": normalize_symbol(symbol),
            "dividends": [
                {"date": idx.isoformat(), "amount": _number(value)}
                for idx, value in dividends.items()
            ],
            "splits": [
                {"date": idx.isoformat(), "ratio": _number(value)}
                for idx, value in splits.items()
            ],
        }

    def earnings_calendar(self, symbol: str) -> dict[str, Any]:
        ticker = self.ticker(symbol)
        calendar = ticker.calendar
        result: dict[str, Any] = {"ticker": symbol.strip().upper()}

        if hasattr(calendar, "to_dict"):
            raw = calendar.to_dict()
            # DataFrames are column-oriented; convert simple scalars/lists.
            result["calendar"] = _jsonable(raw)
        elif isinstance(calendar, dict):
            result["calendar"] = _jsonable(calendar)
        else:
            result["calendar"] = str(calendar)

        return result


def _google_news_rss(
    symbol: str,
    count: int,
) -> list[dict[str, Any]]:
    """Fetch a small set of India-focused headlines from Google News RSS."""

    if symbol == "^NSEI":
        query = "NIFTY 50 NSE India"
    else:
        base_symbol = symbol.removesuffix(".NS")
        query = f"{base_symbol} stock India"

    url = (
        "https://news.google.com/rss/search"
        f"?q={quote_plus(query)}"
        "&hl=en-IN"
        "&gl=IN"
        "&ceid=IN:en"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=8,
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)

        result: list[dict[str, Any]] = []

        for item in root.findall(".//item")[:count]:
            title = item.findtext("title")
            published = item.findtext("pubDate")
            link = item.findtext("link")

            source_node = item.find("source")
            publisher = (
                source_node.text
                if source_node is not None
                else None
            )

            if not title:
                continue

            result.append({
                "title": title,
                "publisher": publisher,
                "published": published,
                "url": link,
            })

        return result

    except Exception:
        logger.exception(
            "Google News RSS fallback failed for %s.",
            symbol,
        )
        return []


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return round(number, 6)


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return round(number, 4)


def _trend_signal(latest: float, sma20: Any, sma50: Any) -> str:
    try:
        s20 = float(sma20)
        s50 = float(sma50)
    except (TypeError, ValueError):
        return "insufficient_data"

    if latest > s20 > s50:
        return "price_above_20_and_50_day_averages"
    if latest < s20 < s50:
        return "price_below_20_and_50_day_averages"
    return "mixed"


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    return value
