"""Persistent, per-user SQLite-backed stock watchlist."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import settings
from finance_agent.providers.yahoo import YahooProvider


class WatchlistStore:
    """SQLite-backed watchlist scoped to the authenticated user."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(owner_id, ticker)
                )
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_watchlist_owner
                ON watchlist(owner_id)
                """
            )

            conn.commit()

    def add(self, ticker: str, user_id: str) -> dict[str, Any]:
        ticker = ticker.strip().upper()

        if not ticker:
            raise ValueError("Ticker cannot be empty.")

        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO watchlist
                    (owner_id, ticker, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, ticker, created_at),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return {
                    "ticker": ticker,
                    "added": False,
                    "message": "Ticker is already in the watchlist.",
                }

            return {
                "id": cursor.lastrowid,
                "ticker": ticker,
                "added": True,
            }

    def remove(self, ticker: str, user_id: str) -> bool:
        ticker = ticker.strip().upper()

        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM watchlist
                WHERE ticker = ? AND owner_id = ?
                """,
                (ticker, user_id),
            )
            conn.commit()

            return cursor.rowcount > 0

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ticker, created_at
                FROM watchlist
                WHERE owner_id = ?
                ORDER BY id
                """,
                (user_id,),
            ).fetchall()

        columns = ["id", "ticker", "created_at"]

        return [
            dict(zip(columns, row))
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