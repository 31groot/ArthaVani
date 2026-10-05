"""NSE market-calendar helpers using the official NSE holiday API."""

from __future__ import annotations

from datetime import datetime, time
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import requests

NSE_TIMEZONE = ZoneInfo("Asia/Kolkata")

NSE_HOLIDAY_API = (
    "https://www.nseindia.com/api/holiday-master?type=trading"
)

NSE_HOME_URL = "https://www.nseindia.com/"

EQUITY_OPEN = time(9, 15)
EQUITY_CLOSE = time(15, 30)

REQUEST_TIMEOUT_SECONDS = 10

#  send browser-like headers because NSE may reject or
#  treat plain automated requests differently

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": NSE_HOME_URL,
    "Accept-Language": "en-US,en;q=0.9",
}


@lru_cache(maxsize=1)
def _nse_session() -> requests.Session:
    """Create a reusable NSE HTTP session."""

    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    # Warm the NSE session first so cookies are established.
    response = session.get(
        NSE_HOME_URL,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    return session


@lru_cache(maxsize=8)
def _trading_holidays(year: int) -> dict[str, dict[str, Any]]:
    """
    Fetch the official NSE trading holiday calendar for a year.

    The NSE endpoint returns multiple market segments. The CM segment
    corresponds to the capital-market/equity holiday calendar.
    """

    session = _nse_session()

    response = session.get(
        NSE_HOLIDAY_API,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    payload = response.json()

    holidays = payload.get("CM")

    if not isinstance(holidays, list):
        raise RuntimeError(
            "NSE holiday API returned an unexpected response."
        )

    result: dict[str, dict[str, Any]] = {}

    for holiday in holidays:
        if not isinstance(holiday, dict):
            continue

        trading_date = holiday.get("tradingDate")

        if not trading_date:
            continue

        try:
            parsed = datetime.strptime(
                trading_date,
                "%d-%b-%Y",
            )
        except ValueError:
            continue

        if parsed.year != year:
            continue

        result[parsed.date().isoformat()] = holiday

    return result


def market_status(at: datetime | None = None) -> dict[str, Any]:
    """
    Return the current NSE equity-market status.

    Uses the official NSE trading-holiday calendar and the regular
    equity-market session of 09:15-15:30 IST.
    """

    moment = (
        at.astimezone(NSE_TIMEZONE)
        if at is not None
        else datetime.now(NSE_TIMEZONE)
    )

    date_key = moment.date().isoformat()

    # Saturday = 5, Sunday = 6
    if moment.weekday() >= 5:
        return {
            "exchange": "NSE",
            "segment": "equity",
            "open": False,
            "reason": "weekend",
            "datetime_ist": moment.isoformat(),
        }

    holidays = _trading_holidays(moment.year)
    holiday = holidays.get(date_key)

    if holiday:
        description = str(
            holiday.get("description") or "NSE trading holiday"
        )

        # NSE marks some dates as special-session dates, such as
        # Diwali Laxmi Pujan / Muhurat Trading.
        is_special_session = "*" in description

        return {
            "exchange": "NSE",
            "segment": "equity",
            "open": False,
            "reason": (
                "special_session"
                if is_special_session
                else "holiday"
            ),
            "holiday": description.rstrip("*").strip(),
            "special_session": is_special_session,
            "datetime_ist": moment.isoformat(),
        }

    current_time = moment.time()

    is_open = EQUITY_OPEN <= current_time <= EQUITY_CLOSE

    return {
        "exchange": "NSE",
        "segment": "equity",
        "open": is_open,
        "reason": (
            "regular_session"
            if is_open
            else "outside_regular_session"
        ),
        "regular_session": "09:15-15:30 IST",
        "datetime_ist": moment.isoformat(),
    }