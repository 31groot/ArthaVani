"""Dashboard aggregation endpoints."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends

from api.security import get_current_user
from config.logger import logger
from finance_agent.providers.market import market_status
from finance_agent.providers.yahoo import YahooProvider
from finance_agent.tools import get_portfolio_summary_for_user

_yahoo = YahooProvider()
_market_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 60.0  # seconds


def _sort_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: str(item.get("published") or ""), reverse=True)


async def _get_cached_market_news() -> list[dict[str, Any]]:
    now = time.monotonic()
    cached = _market_cache.get("market_news")
    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1]
    try:
        data = await asyncio.to_thread(_yahoo.news, "^NSEI", 8)
        _market_cache["market_news"] = (now, data)
        return data
    except Exception:
        logger.exception("Market-news fetch failed.")
        return cached[1] if cached else []


async def _get_cached_market_status() -> dict[str, Any]:
    now = time.monotonic()
    cached = _market_cache.get("market_status")
    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1]
    try:
        data = await asyncio.to_thread(market_status)
        _market_cache["market_status"] = (now, data)
        return data
    except Exception:
        logger.exception("Market-status fetch failed.")
        return {
            "exchange": "NSE",
            "segment": "equity",
            "open": None,
            "reason": "status_unavailable",
            "status_verified": False,
        }


async def build_dashboard(user_id: str) -> dict[str, Any]:
    # Run Portfolio, Market News, and Market Status IN PARALLEL
    portfolio, market_news, current_market_status = await asyncio.gather(
        asyncio.to_thread(get_portfolio_summary_for_user, user_id),
        _get_cached_market_news(),
        _get_cached_market_status(),
    )

    holding_symbols = [
        str(row.get("trading_symbol") or "").strip().upper()
        for row in portfolio.get("holdings", [])
        if row.get("trading_symbol")
    ]

    async def fetch_holding_news(symbol: str) -> list[dict[str, Any]]:
        cache_key = f"news:{symbol}"
        now = time.monotonic()
        cached = _market_cache.get(cache_key)
        if cached and (now - cached[0]) < 300.0:  # 5-min cache for ticker news
            return cached[1]
        try:
            ticker = symbol if "." in symbol else f"{symbol}.NS"
            rows = await asyncio.to_thread(_yahoo.news, ticker, 4)
            for row in rows:
                row["ticker"] = symbol
            _market_cache[cache_key] = (now, rows)
            return rows
        except Exception:
            logger.exception("Holding news fetch failed for %s.", symbol)
            return []

    batches = await asyncio.gather(
        *(fetch_holding_news(symbol) for symbol in holding_symbols[:5])
    )

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for batch in batches:
        for item in batch:
            title = str(item.get("title") or "").strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            merged.append(item)

    hot_news = _sort_news(merged)[:8]
    if not hot_news:
        hot_news = [{**item, "ticker": None} for item in _sort_news(market_news)[:8]]

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "market_status": current_market_status,
        "portfolio": portfolio,
        "market_news": _sort_news(market_news)[:8],
        "hot_news": hot_news,
    }


async def dashboard_endpoint(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return await build_dashboard(user["id"])