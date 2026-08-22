"""Validated, read-only finance queries used by the MCP tool layer."""

from __future__ import annotations

from pathlib import Path

from personal_finance_mcp.database import DATA_AS_OF, DEFAULT_DATABASE_PATH, open_read_only_database
from personal_finance_mcp.quotes import YahooFinanceQuoteProvider


class PersonalFinanceService:
    VALID_ACCOUNT_TYPES = frozenset({"checking", "savings", "credit_card"})
    VALID_PERIODS = frozenset({"this_month", "last_month", "last_30_days", "year_to_date"})

    def __init__(self, database_path: Path = DEFAULT_DATABASE_PATH, quote_provider=None) -> None:
        self.database_path = database_path
        self.quote_provider = quote_provider or YahooFinanceQuoteProvider()

    @staticmethod
    def _money(cents: int) -> float:
        return round(cents / 100, 2)

    def _validate_account_type(self, account_type: str) -> str:
        if not isinstance(account_type, str):
            raise ValueError("account_type must be a string")
        normalized = account_type.strip().lower()
        if normalized not in self.VALID_ACCOUNT_TYPES:
            allowed = ", ".join(sorted(self.VALID_ACCOUNT_TYPES))
            raise ValueError(f"Invalid account_type '{account_type}'. Use one of: {allowed}.")
        return normalized

    def get_account_balance(self, account_type: str) -> dict[str, object]:
        account_type = self._validate_account_type(account_type)
        with open_read_only_database(self.database_path) as connection:
            row = connection.execute(
                "SELECT institution, nickname, balance_cents, currency FROM accounts WHERE account_type = ?",
                (account_type,),
            ).fetchone()
        return {
            "account_type": account_type,
            "institution": row["institution"],
            "nickname": row["nickname"],
            "balance": self._money(row["balance_cents"]),
            "currency": row["currency"],
            "data_as_of": DATA_AS_OF,
        }

    def get_transaction_history(self, account_type: str, n: int) -> dict[str, object]:
        account_type = self._validate_account_type(account_type)
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 50:
            raise ValueError("n must be an integer from 1 to 50")
        with open_read_only_database(self.database_path) as connection:
            rows = connection.execute(
                """SELECT posted_on, merchant, category, amount_cents, transaction_type, description
                FROM transactions JOIN accounts ON accounts.id = transactions.account_id
                WHERE accounts.account_type = ?
                ORDER BY posted_on DESC, transactions.id DESC LIMIT ?""",
                (account_type, n),
            ).fetchall()
        return {
            "account_type": account_type,
            "transactions": [
                {
                    "date": row["posted_on"], "merchant": row["merchant"],
                    "category": row["category"], "amount": self._money(row["amount_cents"]),
                    "type": row["transaction_type"], "description": row["description"],
                }
                for row in rows
            ],
            "data_as_of": DATA_AS_OF,
        }

    def get_portfolio_summary(self) -> dict[str, object]:
        with open_read_only_database(self.database_path) as connection:
            rows = connection.execute(
                "SELECT ticker, name, shares, price_cents, cost_basis_cents FROM holdings ORDER BY ticker"
            ).fetchall()
        holdings = [
            {
                "ticker": row["ticker"], "name": row["name"], "shares": row["shares"],
                "market_value": self._money(round(row["shares"] * row["price_cents"])),
                "unrealized_gain": self._money(round(row["shares"] * row["price_cents"]) - row["cost_basis_cents"]),
            }
            for row in rows
        ]
        return {
            "holdings": holdings,
            "total_market_value": round(sum(item["market_value"] for item in holdings), 2),
            "currency": "USD",
            "data_as_of": DATA_AS_OF,
        }

    def get_expense_breakdown(self, period: str) -> dict[str, object]:
        if not isinstance(period, str):
            raise ValueError("period must be a string")
        normalized = period.strip().lower()
        if normalized not in self.VALID_PERIODS:
            allowed = ", ".join(sorted(self.VALID_PERIODS))
            raise ValueError(f"Invalid period '{period}'. Use one of: {allowed}.")
        ranges = {
            "this_month": ("2026-08-01", "2026-08-22"),
            "last_month": ("2026-07-01", "2026-07-31"),
            "last_30_days": ("2026-07-24", "2026-08-22"),
            "year_to_date": ("2026-01-01", "2026-08-22"),
        }
        start, end = ranges[normalized]
        with open_read_only_database(self.database_path) as connection:
            rows = connection.execute(
                """SELECT category, -SUM(amount_cents) AS total_cents
                FROM transactions
                WHERE transaction_type = 'expense' AND posted_on BETWEEN ? AND ?
                GROUP BY category ORDER BY total_cents DESC, category ASC""",
                (start, end),
            ).fetchall()
        categories = [{"category": row["category"], "amount": self._money(row["total_cents"])} for row in rows]
        return {
            "period": normalized,
            "start_date": start,
            "end_date": end,
            "categories": categories,
            "total_expenses": round(sum(item["amount"] for item in categories), 2),
            "currency": "USD",
            "data_as_of": DATA_AS_OF,
        }

    def get_stock_quote(self, ticker: str) -> dict[str, object]:
        return self.quote_provider.get_quote(ticker)
