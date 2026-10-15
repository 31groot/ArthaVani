"""Dashboard aggregation endpoints."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Awaitable

from fastapi import Depends

from api.security import get_current_user
from config.logger import logger
from finance_agent.providers.market import market_status
from finance_agent.providers.yahoo import YahooProvider
from finance_agent.tools import get_portfolio_summary_for_user


_yahoo = YahooProvider()

_market_cache: dict[str, tuple[float, Any]] = {}

CACHE_TTL = 60.0
TICKER_NEWS_TTL = 300.0

# Keep references to background tasks so they remain alive until completion.
_background_tasks: set[asyncio.Task[None]] = set()

# Prevent duplicate background refreshes for the same ticker.
_ticker_refreshing: set[str] = set()


def _sort_news(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort news from newest to oldest."""
    return sorted(
        items,
        key=lambda item: str(item.get("published") or ""),
        reverse=True,
    )


async def _timed_stage(
    name: str,
    awaitable: Awaitable[Any],
) -> Any:
    """Log the duration of an individual dashboard operation."""
    started = time.perf_counter()

    try:
        return await awaitable
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000

        logger.info(
            "Dashboard stage=%s duration_ms=%.1f",
            name,
            elapsed_ms,
        )


async def _get_cached_market_news() -> list[dict[str, Any]]:
    """Return cached market news or fetch fresh news."""
    now = time.monotonic()
    cached = _market_cache.get("market_news")

    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1]

    try:
        data = await asyncio.to_thread(
            _yahoo.news,
            "^NSEI",
            8,
        )

        _market_cache["market_news"] = (
            time.monotonic(),
            data,
        )

        return data

    except Exception:
        logger.exception("Market-news fetch failed.")

        return cached[1] if cached else []


async def _get_cached_market_status() -> dict[str, Any]:
    """Return cached market status or fetch an updated status."""
    now = time.monotonic()
    cached = _market_cache.get("market_status")

    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1]

    try:
        data = await asyncio.to_thread(market_status)

        _market_cache["market_status"] = (
            time.monotonic(),
            data,
        )

        return data

    except Exception:
        logger.exception("Market-status fetch failed.")

        # Preserve the most recent result if refreshing failed.
        if cached:
            return cached[1]

        return {
            "exchange": "NSE",
            "segment": "equity",
            "open": None,
            "reason": "status_unavailable",
            "status_verified": False,
        }


async def _refresh_holding_news(
    symbol: str,
    cache_key: str,
) -> None:
    """Refresh ticker news in the background."""
    started = time.perf_counter()

    try:
        ticker = (
            symbol
            if "." in symbol
            else f"{symbol}.NS"
        )

        rows = await asyncio.to_thread(
            _yahoo.news,
            ticker,
            4,
        )

        # Avoid modifying the provider's original dictionaries.
        normalized_rows = [
            {
                **row,
                "ticker": symbol,
            }
            for row in rows
        ]

        _market_cache[cache_key] = (
            time.monotonic(),
            normalized_rows,
        )

    except Exception:
        logger.exception(
            "Holding news refresh failed for %s.",
            symbol,
        )

    finally:
        _ticker_refreshing.discard(cache_key)

        elapsed_ms = (
            time.perf_counter() - started
        ) * 1000

        logger.info(
            "Ticker-news refresh symbol=%s duration_ms=%.1f",
            symbol,
            elapsed_ms,
        )


def _schedule_holding_news_refresh(
    symbol: str,
) -> None:
    """Schedule a ticker-news refresh without blocking the response."""
    cache_key = f"news:{symbol}"

    if cache_key in _ticker_refreshing:
        return

    _ticker_refreshing.add(cache_key)

    try:
        task = asyncio.create_task(
            _refresh_holding_news(symbol, cache_key)
        )

        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    except Exception:
        _ticker_refreshing.discard(cache_key)
        logger.exception(
            "Could not schedule ticker-news refresh for %s.",
            symbol,
        )


def _get_cached_holding_news(
    symbols: list[str],
) -> list[list[dict[str, Any]]]:
    """Use cached ticker news and schedule missing or expired refreshes."""
    batches: list[list[dict[str, Any]]] = []
    now = time.monotonic()

    for symbol in symbols:
        cache_key = f"news:{symbol}"
        cached = _market_cache.get(cache_key)

        if cached is not None:
            # Existing news can be returned while a refresh runs.
            batches.append(cached[1])

            if now - cached[0] >= TICKER_NEWS_TTL:
                _schedule_holding_news_refresh(symbol)

        else:
            # Do not make the dashboard wait for a first-time fetch.
            _schedule_holding_news_refresh(symbol)

    return batches


async def build_dashboard(user_id: str) -> dict[str, Any]:
    """Build the dashboard without waiting for ticker-news refreshes."""
    started = time.perf_counter()

    # Run the three primary operations concurrently.
    portfolio, market_news, current_market_status = await asyncio.gather(
        _timed_stage(
            "portfolio",
            asyncio.to_thread(
                get_portfolio_summary_for_user,
                user_id,
            ),
        ),
        _timed_stage(
            "market_news",
            _get_cached_market_news(),
        ),
        _timed_stage(
            "market_status",
            _get_cached_market_status(),
        ),
    )

    # De-duplicate symbols while preserving their original order.
    holding_symbols = list(
        dict.fromkeys(
            str(row.get("trading_symbol") or "").strip().upper()
            for row in portfolio.get("holdings", [])
            if row.get("trading_symbol")
            and str(row.get("trading_symbol")).strip()
        )
    )[:5]

    # Use cached news immediately. Missing or expired news is refreshed
    # asynchronously and does not delay the dashboard response.
    batches = _get_cached_holding_news(holding_symbols)

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
        hot_news = [
            {
                **item,
                "ticker": None,
            }
            for item in _sort_news(market_news)[:8]
        ]

    elapsed_ms = (
        time.perf_counter() - started
    ) * 1000

    logger.info(
        "Dashboard aggregation duration_ms=%.1f ticker_count=%d",
        elapsed_ms,
        len(holding_symbols),
    )

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
    """Return dashboard data for the authenticated user."""
    return await build_dashboard(user["id"])