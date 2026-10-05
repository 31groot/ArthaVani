from datetime import datetime
from zoneinfo import ZoneInfo

from finance_agent.providers.market import market_status


def test_market_status_outside_regular_hours_does_not_require_nse():
    moment = datetime(
        2026,
        10,
        6,
        1,
        0,
        tzinfo=ZoneInfo("Asia/Kolkata"),
    )

    result = market_status(moment)

    assert result["open"] is False
    assert result["reason"] == "outside_regular_session"
