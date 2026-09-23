"""Dashboard aggregation endpoints."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends

from api.security import get_current_user
from config.logger import logger
from finance_agent.providers.market import market_status
from finance_agent.providers.yahoo import YahooProvider
from finance_agent.tools import get_portfolio_summary
from finance_agent.user_context import user_scope


def _sort_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> str:
        return str(item.get("published") or "")

    return sorted(items, key=key, reverse=True)


async def build_dashboard(user_id: str) -> dict[str, Any]:
    with user_scope(user_id):
        portfolio = await get_portfolio_summary.ainvoke({})

    yahoo = YahooProvider()

    market_news: list[dict[str, Any]] = []
    hot_news: list[dict[str, Any]] = []

    try:
        market_news = await asyncio.to_thread(
            yahoo.news,
            "^NSEI",
            8,
        )
    except Exception:
        logger.exception("Market-news fetch failed.")

    holding_symbols = [
        str(row.get("trading_symbol") or "").strip().upper()
        for row in portfolio.get("holdings", [])
        if row.get("trading_symbol")
    ]

    # Keep the dashboard responsive: fetch recent news for only the first
    # five holdings and cap each ticker to a few headlines.
    async def fetch_holding_news(symbol: str) -> list[dict[str, Any]]:
        try:
            ticker = symbol if "." in symbol else f"{symbol}.NS"
            rows = await asyncio.to_thread(yahoo.news, ticker, 4)
            for row in rows:
                row["ticker"] = symbol
            return rows
        except Exception:
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

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "market_status": market_status(),
        "portfolio": portfolio,
        "market_news": _sort_news(market_news)[:8],
        "hot_news": hot_news,
    }


async def dashboard_endpoint(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return await build_dashboard(user["id"])
