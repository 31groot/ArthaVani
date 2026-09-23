# ArthaVani native finance tools bundle

This bundle removes the MCP dependency from the agent and adds native LangGraph
tools for Groww, Yahoo Finance, AMFI, FX, NSE market status, corporate actions,
technical analysis, portfolio analytics, and persistent watchlists.

Zerodha direct API integration is intentionally NOT included.

Sources/assumptions:
- Groww current portfolio/live data uses the official Groww Python SDK.
- Groww LTP supports up to 50 instruments per call and is used for live portfolio
  valuation.
- AMFI latest NAV data is read from its published NAV report.
- FX uses Frankfurter v2, which requires no API key.
- NSE market status uses the current 2026 equity holiday calendar embedded from
  NSE's published calendar. Update it annually.
- Yahoo Finance functionality uses yfinance and is read-only.

Important:
- Watchlist tools persist local price alerts and expose `watchlist_check()`.
  Automatic spoken/push scheduling is intentionally left separate from the
  data/tool layer.
- Portfolio current value and P&L use Groww LTP in one batched request where
  possible.
