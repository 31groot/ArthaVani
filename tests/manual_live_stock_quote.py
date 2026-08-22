"""Manual network check for the live Yahoo Finance quote provider.

Run explicitly; it is intentionally not part of the unit-test suite:
    ./.venv/bin/python tests/manual_live_stock_quote.py AAPL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Direct script execution makes tests/ the import root; add the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from personal_finance_mcp.quotes import YahooFinanceQuoteProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a live Yahoo Finance quote.")
    parser.add_argument("ticker", nargs="?", default="AAPL")
    arguments = parser.parse_args()
    quote = YahooFinanceQuoteProvider().get_quote(arguments.ticker)
    print(json.dumps(quote, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
