
"""Native LangGraph finance tools for ArthaVani."""
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Any

from langchain_core.tools import tool

from config.settings import settings
from finance_agent.providers.amfi import AMFIProvider
from finance_agent.providers.forex import ForexProvider
from finance_agent.providers.groww import (
    decimal,
    get_groww_provider,
    holding_rows,
    preferred_exchange,
)
from finance_agent.providers.market import market_status
from finance_agent.providers.yahoo import YahooProvider
from finance_agent.providers.watchlist import WatchlistStore, check_watchlist


@lru_cache(maxsize=1)
def _yahoo() -> YahooProvider:
    return YahooProvider()


@lru_cache(maxsize=1)
def _amfi() -> AMFIProvider:
    return AMFIProvider()


@lru_cache(maxsize=1)
def _forex() -> ForexProvider:
    return ForexProvider()


@lru_cache(maxsize=1)
def _watchlist() -> WatchlistStore:
    return WatchlistStore(settings.WATCHLIST_DB_PATH)


def _yahoo_equity_symbol(exchange: str, trading_symbol: str) -> str:
    """Map an Indian equity exchange/trading symbol to Yahoo Finance."""
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    return f"{trading_symbol.strip().upper()}{suffix}"


def _portfolio_snapshot() -> dict[str, Any]:
    try:
        holdings_payload = get_groww_provider().get_holdings()
    except Exception as exc:
        return {
            "holding_count": None,
            "invested_value": None,
            "current_value": None,
            "profit_loss": None,
            "profit_loss_percentage": None,
            "top_holding": None,
            "holdings": [],
            "allocation": [],
            "currency": "INR",
            "portfolio_data_available": False,
            "market_data_available": False,
            "market_data_realtime": False,
            "valuation_basis": "unavailable",
            "price_freshness": "unavailable",
            "price_source": "unavailable",
            "market_data_error": (
                f"Groww portfolio access failed: {type(exc).__name__}: {exc}"
            ),
        }

    rows = holding_rows(holdings_payload)
    if not rows:
        return {
            "holding_count": 0,
            "invested_value": 0.0,
            "current_value": None,
            "profit_loss": None,
            "profit_loss_percentage": None,
            "top_holding": None,
            "holdings": [],
            "allocation": [],
            "currency": "INR",
            "portfolio_data_available": True,
            "market_data_available": True,
            "valuation_basis": "none",
            "market_data_error": None,
        }

    requests: list[str] = []
    request_map: dict[int, str] = {}

    for index, row in enumerate(rows):
        exchange = preferred_exchange(row)
        symbol = str(row.get("trading_symbol") or "").strip().upper()
        if not symbol:
            continue

        request_symbol = f"{exchange}_{symbol}"
        requests.append(request_symbol)
        request_map[index] = request_symbol

    # Try Groww first because its live-data API is the authoritative source
    # for the broker portfolio. If Groww rejects live data, try individual
    # Groww quotes and finally Yahoo Finance as an explicitly labelled
    # fallback. Yahoo is not treated as real-time market data here.
    ltp: dict[str, Any] = {}
    market_data_error: str | None = None
    groww_live_available = False

    if requests:
        try:
            response = get_groww_provider().get_ltp("CASH", requests)
            if isinstance(response, dict):
                ltp = response
                groww_live_available = all(
                    request_symbol in ltp for request_symbol in requests
                )
            else:
                market_data_error = "Groww returned an unexpected LTP response."
        except Exception as exc:
            market_data_error = f"Groww batch LTP failed: {type(exc).__name__}"

    if requests and not groww_live_available:
        for index, request_symbol in request_map.items():
            if request_symbol in ltp:
                continue

            exchange, symbol = request_symbol.split("_", 1)
            try:
                quote = get_groww_provider().get_quote(
                    exchange=exchange,
                    segment="CASH",
                    trading_symbol=symbol,
                )
            except Exception:
                continue

            if not isinstance(quote, dict):
                continue

            price = None
            for key in ("last_price", "ltp", "close"):
                if quote.get(key) is not None:
                    price = quote[key]
                    break

            if price is not None:
                ltp[request_symbol] = price

        groww_live_available = bool(requests) and all(
            request_symbol in ltp for request_symbol in requests
        )

    yahoo_prices: dict[str, dict[str, Any]] = {}
    yahoo_errors: list[str] = []

    if not groww_live_available:
        for index, request_symbol in request_map.items():
            if request_symbol in ltp:
                continue

            exchange, symbol = request_symbol.split("_", 1)
            yahoo_symbol = _yahoo_equity_symbol(exchange, symbol)
            try:
                quote = _yahoo().quote(yahoo_symbol)
                price = quote.get("latest_price")
                if price is None:
                    raise ValueError("Yahoo quote did not contain latest_price")

                ltp[request_symbol] = price
                yahoo_prices[request_symbol] = {
                    "ticker": yahoo_symbol,
                    "data_timestamp": quote.get("data_timestamp"),
                }
            except Exception as exc:
                yahoo_errors.append(
                    f"{symbol}: {type(exc).__name__}"
                )

    yahoo_fallback_used = bool(yahoo_prices)

    if not groww_live_available and yahoo_fallback_used:
        market_data_error = (
            f"Groww live market data unavailable; using Yahoo Finance fallback "
            f"for {len(yahoo_prices)} holding(s)."
        )
        if yahoo_errors:
            market_data_error += " Yahoo failures: " + ", ".join(yahoo_errors)
    elif not groww_live_available and yahoo_errors:
        market_data_error = (
            market_data_error
            or "Groww live market data unavailable."
        ) + " Yahoo failures: " + ", ".join(yahoo_errors)

    invested_total = Decimal("0")
    output_rows: list[dict[str, Any]] = []
    all_prices_available = True

    for index, row in enumerate(rows):
        symbol = str(row.get("trading_symbol") or "").strip().upper()
        quantity = decimal(
            row.get("quantity")
            or row.get("demat_free_quantity")
        )
        average_price = decimal(row.get("average_price"))
        invested = quantity * average_price
        invested_total += invested

        request_symbol = request_map.get(index)
        current_price_value = (
            ltp.get(request_symbol)
            if isinstance(ltp, dict) and request_symbol
            else None
        )

        current_price = None
        current_value = None
        pnl = None
        pnl_pct = None
        price_source = "unavailable"

        if current_price_value is not None:
            try:
                current_price = Decimal(str(current_price_value))
            except Exception:
                current_price = None

        if current_price is not None:
            current_value = quantity * current_price
            pnl = current_value - invested
            pnl_pct = (
                (pnl / invested) * Decimal("100")
                if invested
                else Decimal("0")
            )

            if request_symbol in yahoo_prices:
                price_source = "yahoo_fallback"
                price_freshness = "delayed_or_unknown"
            else:
                price_source = "groww_live"
                price_freshness = "real_time"
        else:
            all_prices_available = False
            price_freshness = "unavailable"

        exchanges = row.get("tradable_exchanges") or []

        # Allocation remains useful even when live prices are unavailable,
        # so fall back to cost basis for allocation only. This must never be
        # presented as current market value.
        allocation_value = (
            current_value
            if current_value is not None
            else invested
        )

        output_rows.append({
            "trading_symbol": symbol,
            "quantity": float(quantity),
            "average_price": float(average_price),
            "current_price": (
                float(current_price)
                if current_price is not None
                else None
            ),
            "invested_value": round(float(invested), 2),
            "current_value": (
                round(float(current_value), 2)
                if current_value is not None
                else None
            ),
            "profit_loss": (
                round(float(pnl), 2)
                if pnl is not None
                else None
            ),
            "profit_loss_percentage": (
                round(float(pnl_pct), 2)
                if pnl_pct is not None
                else None
            ),
            "exchange_used": (
                request_symbol.split("_", 1)[0]
                if request_symbol
                else None
            ),
            "tradable_exchanges": exchanges,
            "price_source": price_source,
            "price_freshness": price_freshness,
            "allocation_value": round(float(allocation_value), 2),
        })

    output_rows.sort(
        key=lambda row: row["allocation_value"],
        reverse=True,
    )

    allocation_total = sum(
        Decimal(str(row["allocation_value"]))
        for row in output_rows
    )

    allocation = []
    for row in output_rows:
        weight = (
            (
                Decimal(str(row["allocation_value"]))
                / allocation_total
            ) * Decimal("100")
            if allocation_total
            else Decimal("0")
        )
        allocation.append({
            "trading_symbol": row["trading_symbol"],
            "weight_percentage": round(float(weight), 2),
        })

    market_data_available = bool(output_rows) and all_prices_available

    source_values = {row["price_source"] for row in output_rows if row["current_value"] is not None}
    freshness_values = {row["price_freshness"] for row in output_rows if row["current_value"] is not None}

    if source_values == {"groww_live"}:
        portfolio_price_source = "groww_live"
        portfolio_price_freshness = "real_time"
    elif source_values == {"yahoo_fallback"}:
        portfolio_price_source = "yahoo_fallback"
        portfolio_price_freshness = "delayed_or_unknown"
    elif source_values:
        portfolio_price_source = "mixed"
        portfolio_price_freshness = "mixed"
    else:
        portfolio_price_source = None
        portfolio_price_freshness = "unavailable"

    # Only report aggregate current value and P&L when every holding has
    # a live price. Partial market data must not be presented as a complete
    # portfolio valuation.
    if market_data_available:
        current_total = sum(
            (
                Decimal(str(row["current_value"]))
                for row in output_rows
                if row["current_value"] is not None
            ),
            Decimal("0"),
        )
        overall_pnl = current_total - invested_total
        overall_pnl_pct = (
            (overall_pnl / invested_total) * Decimal("100")
            if invested_total
            else Decimal("0")
        )
    else:
        current_total = None
        overall_pnl = None
        overall_pnl_pct = None

    # allocation_value is an internal calculation aid and should not be
    # mistaken for live current value in the LLM-facing tool result.
    for row in output_rows:
        row.pop("allocation_value", None)

    return {
        "holding_count": len(output_rows),
        "portfolio_data_available": True,
        "invested_value": round(float(invested_total), 2),
        "current_value": (
            round(float(current_total), 2)
            if current_total is not None
            else None
        ),
        "profit_loss": (
            round(float(overall_pnl), 2)
            if overall_pnl is not None
            else None
        ),
        "profit_loss_percentage": (
            round(float(overall_pnl_pct), 2)
            if overall_pnl_pct is not None
            else None
        ),
        "top_holding": output_rows[0]["trading_symbol"] if output_rows else None,
        "holdings": output_rows,
        "allocation": allocation,
        "currency": "INR",
        "market_data_available": market_data_available,
        "market_data_realtime": portfolio_price_freshness == "real_time",
        "valuation_basis": (
            "live_market_value"
            if portfolio_price_source == "groww_live" and market_data_available
            else "fallback_market_value"
            if market_data_available
            else "invested_value"
        ),
        "price_source": portfolio_price_source,
        "price_freshness": portfolio_price_freshness,
        "market_data_error": market_data_error,
    }


@tool
def get_portfolio_summary() -> dict[str, Any]:
    """Get Groww holdings, cost basis, and live valuation/P&L when available."""
    return _portfolio_snapshot()


@tool
def get_portfolio_risk() -> dict[str, Any]:
    """Compute portfolio concentration metrics from live value or cost basis."""
    snapshot = _portfolio_snapshot()

    if not snapshot.get("portfolio_data_available", False):
        return {
            "holding_count": None,
            "largest_holding": None,
            "largest_holding_weight_percentage": None,
            "concentration_hhi": None,
            "interpretation": "portfolio data unavailable",
            "allocation": [],
            "allocation_basis": "unavailable",
            "portfolio_data_available": False,
            "market_data_available": False,
            "market_data_realtime": False,
            "market_data_error": snapshot["market_data_error"],
        }

    holdings = snapshot["holdings"]

    values = [
        Decimal(str(
            row["current_value"]
            if row["current_value"] is not None
            else row["invested_value"]
        ))
        for row in holdings
    ]
    total = sum(values, Decimal("0"))

    weights = [
        (value / total) if total else Decimal("0")
        for value in values
    ]
    hhi = sum(weight * weight for weight in weights)
    top_weight = max(weights, default=Decimal("0"))

    return {
        "holding_count": len(holdings),
        "largest_holding": (
            holdings[0]["trading_symbol"] if holdings else None
        ),
        "largest_holding_weight_percentage": round(
            float(top_weight * Decimal("100")),
            2,
        ),
        "concentration_hhi": round(float(hhi), 4),
        "interpretation": (
            "higher values indicate more concentration"
            if holdings
            else "no holdings"
        ),
        "allocation": snapshot["allocation"],
        "allocation_basis": (
            "live_market_value"
            if snapshot["market_data_available"]
            else "invested_value"
        ),
        "portfolio_data_available": snapshot.get("portfolio_data_available", True),
        "market_data_available": snapshot["market_data_available"],
        "market_data_realtime": snapshot.get("market_data_realtime", False),
        "market_data_error": snapshot["market_data_error"],
    }


@tool
def yahoo_get_quote(ticker: str) -> dict[str, Any]:
    """Get latest Yahoo Finance price and daily change."""
    return _yahoo().quote(ticker)


@tool
def yahoo_get_fundamentals(ticker: str) -> dict[str, Any]:
    """Get common company valuation and growth metrics from Yahoo Finance."""
    return _yahoo().fundamentals(ticker)


@tool
def yahoo_get_history(
    ticker: str,
    period: str = "6mo",
    interval: str = "1d",
) -> list[dict[str, Any]]:
    """Get historical OHLCV data from Yahoo Finance."""
    return _yahoo().history(ticker, period, interval)


@tool
def yahoo_get_technical_analysis(
    ticker: str,
    period: str = "6mo",
) -> dict[str, Any]:
    """Calculate basic SMA and RSI technical indicators."""
    return _yahoo().technical_analysis(ticker, period)


@tool
def yahoo_get_news(
    ticker: str,
    count: int = 5,
) -> list[dict[str, Any]]:
    """Get recent ticker-specific news from Yahoo Finance."""
    return _yahoo().news(ticker, count)


@tool
def yahoo_get_corporate_actions(
    ticker: str,
    period: str = "1y",
) -> dict[str, Any]:
    """Get dividends and stock splits reported by Yahoo Finance."""
    return _yahoo().corporate_actions(ticker, period)


@tool
def yahoo_get_earnings_calendar(ticker: str) -> dict[str, Any]:
    """Get the earnings/event calendar available for a ticker."""
    return _yahoo().earnings_calendar(ticker)


@tool
def amfi_get_latest_nav(
    scheme_query: str,
    limit: int = 5,
) -> dict[str, Any]:
    """Find current mutual-fund NAVs from AMFI's published NAV report."""
    results = _amfi().latest_nav(scheme_query, limit)
    return {
        "results": results,
        "count": len(results),
        "found": bool(results),
        "scheme_query": scheme_query,
    }


@tool
def amfi_get_nav_history(
    scheme_query: str,
    start_date: str,
    end_date: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Get mutual-fund NAV history from AMFI for a date range."""
    results = _amfi().history(
        scheme_query,
        start_date,
        end_date,
        limit,
    )
    return {
        "results": results,
        "count": len(results),
        "found": bool(results),
        "scheme_query": scheme_query,
        "start_date": start_date,
        "end_date": end_date,
    }


@tool
def get_fx_rate(base_currency: str, quote_currency: str) -> dict[str, Any]:
    """Get the latest foreign-exchange rate."""
    return _forex().rate(base_currency, quote_currency)


@tool
def convert_currency(
    amount: float,
    base_currency: str,
    quote_currency: str,
) -> dict[str, Any]:
    """Convert an amount using the latest Frankfurter FX rate."""
    return _forex().convert(amount, base_currency, quote_currency)


@tool
def get_nse_market_status() -> dict[str, Any]:
    """Tell whether the NSE equity market is open right now in India time."""
    return market_status()


@tool
def watchlist_add(
    ticker: str,
    condition: str,
    target_price: float,
) -> dict[str, Any]:
    """Add a persistent price alert, above or below a target."""
    return _watchlist().add(ticker, condition, target_price)


@tool
def watchlist_remove(alert_id: int) -> dict[str, Any]:
    """Remove a saved price alert by ID."""
    return {
        "removed": _watchlist().remove(alert_id),
        "alert_id": alert_id,
    }


@tool
def watchlist_list() -> dict[str, Any]:
    """List active saved price alerts."""
    alerts = _watchlist().list_active()
    return {
        "alerts": alerts,
        "count": len(alerts),
        "has_alerts": bool(alerts),
    }


@tool
def watchlist_check() -> dict[str, Any]:
    """Check active saved price alerts against current Yahoo prices.

    A triggered alert is deactivated after firing once. This tool is the
    polling/checking primitive; a later scheduler can call it periodically.
    """
    triggered = check_watchlist(_watchlist(), _yahoo())
    return {
        "triggered_alerts": triggered,
        "count": len(triggered),
        "has_triggered": bool(triggered),
    }


def build_finance_tools() -> list[Any]:
    """Return the lean native voice-agent finance tool set."""
    return [
        # Portfolio
        get_portfolio_summary,
        get_portfolio_risk,
        # Company / market data
        yahoo_get_quote,
        yahoo_get_fundamentals,
        yahoo_get_history,
        yahoo_get_technical_analysis,
        yahoo_get_news,
        # Mutual funds / FX / market status
        amfi_get_latest_nav,
        amfi_get_nav_history,
        convert_currency,
        get_nse_market_status,
        # Stateful local alerts
        watchlist_add,
        watchlist_remove,
        watchlist_list,
        watchlist_check,
    ]
