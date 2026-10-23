
from __future__ import annotations

from typing import Any
from finance_agent.persistence import db_connection

from finance_agent.providers.yahoo import YahooProvider


class WatchlistStore:
    """PostgreSQL-backed watchlist scoped to the authenticated user."""

    def add(self, ticker: str, user_id: str) -> dict[str, Any]:
        ticker = ticker.strip().upper()

        if not ticker:
            raise ValueError("Ticker cannot be empty.")

        try:
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO arthavani_watchlist
                            (owner_id, ticker)
                        VALUES (%s, %s)
                        ON CONFLICT (owner_id, ticker) DO NOTHING
                        RETURNING id
                        """,
                        (user_id, ticker),
                    )

                    row = cur.fetchone()

                conn.commit()

        except Exception:
            raise

        if row is None:
            return {
                "ticker": ticker,
                "added": False,
                "message": "Ticker is already in the watchlist.",
            }

        return {
            "id": row[0],
            "ticker": ticker,
            "added": True,
        }

    def remove(self, ticker: str, user_id: str) -> bool:
        ticker = ticker.strip().upper()

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM arthavani_watchlist
                    WHERE ticker = %s AND owner_id = %s
                    """,
                    (ticker, user_id),
                )

                removed = cur.rowcount > 0

            conn.commit()

        return removed

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, ticker, created_at
                    FROM arthavani_watchlist
                    WHERE owner_id = %s
                    ORDER BY id
                    """,
                    (user_id,),
                )

                rows = cur.fetchall()

        return [
            {
                "id": row[0],
                "ticker": row[1],
                "created_at": row[2].isoformat(),
            }
            for row in rows
        ]


def get_watchlist_with_prices(
    store: WatchlistStore,
    yahoo: YahooProvider,
    user_id: str,
) -> list[dict[str, Any]]:
    """Return the user's watchlist with current Yahoo prices."""

    items = store.list_for_user(user_id)

    results: list[dict[str, Any]] = []

    for item in items:
        quote = yahoo.quote(item["ticker"])

        results.append(
            {
                **item,
                "current_price": quote.get("latest_price"),
                "change_percent": quote.get("change_percent"),
            }
        )

    return results