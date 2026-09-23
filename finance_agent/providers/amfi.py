
"""Direct reader for AMFI's published mutual-fund NAV files."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import requests

AMFI_LATEST_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
AMFI_HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"


class AMFIProvider:
    """Fetch and parse public AMFI NAV data."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ArthaVani/1.0 mutual-fund research client",
        })

    def latest_nav(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        text = self.session.get(AMFI_LATEST_URL, timeout=15).text
        return _find_schemes(text, query, limit)

    def history(
        self,
        query: str,
        start_date: str,
        end_date: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        start = _parse_date(start_date)
        end = _parse_date(end_date)

        response = self.session.get(
            AMFI_HISTORY_URL,
            params={
                "frmdt": start.strftime("%d-%b-%Y"),
                "todt": end.strftime("%d-%b-%Y"),
            },
            timeout=20,
        )
        response.raise_for_status()
        return _find_schemes(response.text, query, limit)


def _find_schemes(
    text: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    wanted = query.strip().lower()
    if not wanted:
        raise ValueError("scheme query must not be empty")

    results: list[dict[str, Any]] = []
    current_amc = None
    current_category = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = [part.strip() for part in line.split(";")]

        if len(parts) < 6:
            if "mutual fund" in line.lower():
                current_amc = line
            elif "(" in line:
                current_category = line
            continue

        code, isin_growth, isin_reinvestment, name, nav, nav_date = parts[:6]

        if not code.isdigit():
            continue

        if wanted not in name.lower():
            continue

        try:
            nav_value = float(nav)
        except (TypeError, ValueError):
            continue

        results.append({
            "scheme_code": code,
            "isin_growth_or_payout": isin_growth or None,
            "isin_reinvestment": isin_reinvestment or None,
            "scheme_name": name,
            "nav": nav_value,
            "date": nav_date,
            "amc": current_amc,
            "category": current_category,
        })

        if len(results) >= limit:
            break

    return results


def _parse_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        "Date must be YYYY-MM-DD or DD-Mon-YYYY."
    )
