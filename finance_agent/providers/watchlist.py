
"""Persistent local watchlist/price-alert state."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import settings
from finance_agent.providers.yahoo import YahooProvider


class WatchlistStore:
    """Small SQLite-backed alert store for ArthaVani."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    target_price REAL NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_triggered_at TEXT
                )
            """)
            conn.commit()

    def add(self, ticker: str, condition: str, target_price: float) -> dict[str, Any]:
        condition = condition.lower().strip()
        if condition not in {"above", "below"}:
            raise ValueError("condition must be 'above' or 'below'.")

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO alerts
                    (ticker, condition, target_price, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    ticker.strip().upper(),
                    condition,
                    float(target_price),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            return {
                "id": cursor.lastrowid,
                "ticker": ticker.strip().upper(),
                "condition": condition,
                "target_price": float(target_price),
                "active": True,
            }

    def remove(self, alert_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM alerts WHERE id = ?",
                (alert_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_active(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ticker, condition, target_price,
                       active, created_at, last_triggered_at
                FROM alerts
                WHERE active = 1
                ORDER BY id
                """
            ).fetchall()

        columns = [
            "id",
            "ticker",
            "condition",
            "target_price",
            "active",
            "created_at",
            "last_triggered_at",
        ]
        return [dict(zip(columns, row)) for row in rows]

    def mark_triggered(self, alert_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE alerts
                SET active = 0, last_triggered_at = ?
                WHERE id = ?
                """,
                (datetime.utcnow().isoformat(), alert_id),
            )
            conn.commit()


def check_watchlist(
    store: WatchlistStore,
    yahoo: YahooProvider,
) -> list[dict[str, Any]]:
    triggered: list[dict[str, Any]] = []

    for alert in store.list_active():
        quote = yahoo.quote(alert["ticker"])
        price = float(quote["latest_price"])

        crossed = (
            alert["condition"] == "above"
            and price >= float(alert["target_price"])
        ) or (
            alert["condition"] == "below"
            and price <= float(alert["target_price"])
        )

        if crossed:
            store.mark_triggered(alert["id"])
            triggered.append({
                **alert,
                "current_price": price,
                "triggered": True,
            })

    return triggered
