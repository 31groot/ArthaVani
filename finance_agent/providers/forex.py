
"""Lightweight currency provider using Frankfurter's public v2 API."""
from __future__ import annotations

from decimal import Decimal

import requests

API_BASE = "https://api.frankfurter.dev/v2"


class ForexProvider:
    """Read-only foreign-exchange rates; no API key is required."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ArthaVani/1.0 forex client",
        })

    def rate(self, base: str, quote: str) -> dict:
        base = base.strip().upper()
        quote = quote.strip().upper()

        if len(base) != 3 or len(quote) != 3:
            raise ValueError("base and quote must be ISO 4217 currency codes.")

        response = self.session.get(
            f"{API_BASE}/rate/{base}/{quote}",
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        return {
            "date": data["date"],
            "base": data["base"],
            "quote": data["quote"],
            "rate": float(data["rate"]),
        }

    def convert(self, amount: float, base: str, quote: str) -> dict:
        result = self.rate(base, quote)
        converted = Decimal(str(amount)) * Decimal(str(result["rate"]))
        return {
            **result,
            "amount": amount,
            "converted_amount": float(converted),
        }
