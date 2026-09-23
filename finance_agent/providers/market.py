
"""NSE market-calendar helpers plus Yahoo corporate actions."""
from __future__ import annotations

from datetime import datetime, date, time
from zoneinfo import ZoneInfo

NSE_TIMEZONE = ZoneInfo("Asia/Kolkata")

# Current 2026 equity holidays published by NSE.
# Keep this list versioned in code so "is the market open?" is deterministic
# during the current calendar year; update yearly from NSE's official calendar.
NSE_HOLIDAYS_2026 = {
    "2026-01-15": "Municipal Corporation Election in Maharashtra",
    "2026-01-26": "Republic Day",
    "2026-02-19": "Chhatrapati Shivaji Maharaj Jayanti",
    "2026-03-03": "Holi (Second Day)",
    "2026-03-19": "Gudhi Padwa",
    "2026-03-26": "Ram Navami",
    "2026-03-31": "Mahavir Jayanti",
    "2026-04-01": "Annual Bank Closing",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Babasaheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Din / Buddha Pournima",
    "2026-05-28": "Bakri ID (Id-Uz-Zuha)",
    "2026-06-26": "Muharram",
    "2026-08-26": "Id-E-Milad",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali (Bali Pratipada)",
    "2026-11-24": "Guru Nanak Jayanti",
    "2026-12-25": "Christmas",
}

EQUITY_OPEN = time(9, 15)
EQUITY_CLOSE = time(15, 30)


def market_status(at: datetime | None = None) -> dict:
    moment = at.astimezone(NSE_TIMEZONE) if at else datetime.now(NSE_TIMEZONE)
    date_key = moment.date().isoformat()

    if moment.weekday() >= 5:
        return {
            "exchange": "NSE",
            "segment": "equity",
            "open": False,
            "reason": "weekend",
            "datetime_ist": moment.isoformat(),
        }

    holiday = NSE_HOLIDAYS_2026.get(date_key)
    if holiday:
        return {
            "exchange": "NSE",
            "segment": "equity",
            "open": False,
            "reason": "holiday",
            "holiday": holiday,
            "datetime_ist": moment.isoformat(),
        }

    is_open = EQUITY_OPEN <= moment.time() <= EQUITY_CLOSE
    return {
        "exchange": "NSE",
        "segment": "equity",
        "open": is_open,
        "reason": "regular_session" if is_open else "outside_regular_session",
        "regular_session": "09:15-15:30 IST",
        "datetime_ist": moment.isoformat(),
    }
