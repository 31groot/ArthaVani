from pathlib import Path

from personal_finance_mcp.database import (
    DEFAULT_DATABASE_PATH,
    open_read_only_database,
)

from personal_finance_mcp.quotes import (
    YahooFinanceQuoteProvider,
)

from config.constants import DATA_AS_OF


class PersonalFinanceService:

    # Allowed account types.

    # frozenset is used because these values are configuration-like
    # constants and should not be modified at runtime.
    VALID_ACCOUNT_TYPES = frozenset(
        {
            "checking",
            "savings",
            "credit_card",
        }
    )

    # Allowed expense-reporting periods.
    VALID_PERIODS = frozenset(
        {
            "this_month",
            "last_month",
            "last_30_days",
            "year_to_date",
        }
    )

    def __init__(
        self,
        database_path: Path = DEFAULT_DATABASE_PATH,
        quote_provider=None,
    ) -> None:

        # Store the location of the SQLite database.
        
        self.database_path = database_path

        # Store the object responsible for retrieving stock quotes.

        # Instead of hard-coding Yahoo Finance everywhere,
        # the provider can be replaced later.
        self.quote_provider = (
            quote_provider
            or YahooFinanceQuoteProvider()
        )

    @staticmethod
    def _money(
        paise: int,
    ) -> float:

     
        return round(
            paise / 100,
            2,
        )

    def _validate_account_type(
        self,
        account_type: str,
    ) -> str:

        # Make sure the caller provided a string.
        if not isinstance(
            account_type,
            str,
        ):
            raise ValueError(
                "account_type must be a string"
            )

        # Normalize user input:

        normalized = (
            account_type
            .strip()
            .lower()
        )

        # Make sure the normalized value is one of the
        # supported account types.
        if normalized not in self.VALID_ACCOUNT_TYPES:

            allowed = ", ".join(
                sorted(
                    self.VALID_ACCOUNT_TYPES
                )
            )

            raise ValueError(
                f"Invalid account_type '{account_type}'. "
                f"Use one of: {allowed}."
            )

        return normalized

    def get_account_balance(
        self,
        account_type: str,
    ) -> dict[str, object]:

        # Validate and normalize the requested account type.
        
        account_type = self._validate_account_type(
            account_type
        )

        # Open the SQLite database in read-only mode.

        with open_read_only_database(
            self.database_path
        ) as connection:

            # Find the account matching the requested type.
            #
            # The ? is a parameter placeholder.
            #
            # (account_type,) supplies the value safely.

            row = connection.execute(
                """
                SELECT
                    institution,
                    nickname,
                    balance_paise,
                    currency
                FROM accounts
                WHERE account_type = ?
                """,
                (account_type,),
            ).fetchone()

        # Return a clean dictionary for the MCP layer.

        return {
            "account_type": account_type,
            "institution": row["institution"],
            "nickname": row["nickname"],

            # Convert paise into normal currency units.
            "balance": self._money(
                row["balance_paise"]
            ),

            "currency": row["currency"],

            # Tell the caller what date the demo data represents.
            "data_as_of": DATA_AS_OF,
        }

    def get_transaction_history(
        self,
        account_type: str,
        n: int,
    ) -> dict[str, object]:

        # Validate and normalize the account type.
        account_type = self._validate_account_type(
            account_type
        )

        if (
            isinstance(n, bool)
            or not isinstance(n, int)
            or not 1 <= n <= 50
        ):

            raise ValueError(
                "n must be an integer from 1 to 50"
            )

        # Open a read-only database connection.
        with open_read_only_database(
            self.database_path
        ) as connection:

            # Retrieve recent transactions for the requested
            # account type.

            rows = connection.execute(
                """
                SELECT
                    posted_on,
                    merchant,
                    category,
                    amount_paise,
                    transaction_type,
                    description
                FROM transactions
                JOIN accounts
                    ON accounts.id = transactions.account_id
                WHERE accounts.account_type = ?
                ORDER BY
                    posted_on DESC,
                    transactions.id DESC
                LIMIT ?
                """,
                (
                    account_type,
                    n,
                ),
            ).fetchall()

        # Convert database rows into normal dictionaries.

        return {
            "account_type": account_type,

            "transactions": [
                {
                    "date": row["posted_on"],
                    "merchant": row["merchant"],
                    "category": row["category"],

                    # Convert paise to normal currency.
                    "amount": self._money(
                        row["amount_paise"]
                    ),

                    "type": row["transaction_type"],
                    "description": row["description"],
                }

                for row in rows
            ],

            "data_as_of": DATA_AS_OF,
        }

    def get_portfolio_summary(
        self,
    ) -> dict[str, object]:

        # Open the database in read-only mode.
        with open_read_only_database(
            self.database_path
        ) as connection:

            # Retrieve all investment holdings.

            rows = connection.execute(
                """
                SELECT
                    ticker,
                    name,
                    shares,
                    price_paise,
                    cost_basis_paise
                FROM holdings
                ORDER BY ticker
                """
            ).fetchall()

        # Build a clean representation of each holding.
        holdings = [
            {
                "ticker": row["ticker"],
                "name": row["name"],
                "shares": row["shares"],

                # Calculate current market value:
                
                "market_value": self._money(
                    round(
                        row["shares"]
                        * row["price_paise"]
                    )
                ),

                # Unrealized gain means:

                "unrealized_gain": self._money(
                    round(
                        row["shares"]
                        * row["price_paise"]
                    )
                    - row["cost_basis_paise"]
                ),
            }

            for row in rows
        ]

        # Return the complete portfolio summary.
        return {
            "holdings": holdings,

            # Sum the market values of all holdings.
            "total_market_value": round(
                sum(
                    item["market_value"]
                    for item in holdings
                ),
                2,
            ),

            # Current demo portfolio data is stored in USD.
            "currency": "USD",

            "data_as_of": DATA_AS_OF,
        }

    def get_expense_breakdown(
        self,
        period: str,
    ) -> dict[str, object]:

        # The period must be a string.
        if not isinstance(
            period,
            str,
        ):
            raise ValueError(
                "period must be a string"
            )

        # Normalize user input.
        
        normalized = (
            period
            .strip()
            .lower()
        )

        # Make sure the requested period is supported.
        if normalized not in self.VALID_PERIODS:

            allowed = ", ".join(
                sorted(
                    self.VALID_PERIODS
                )
            )

            raise ValueError(
                f"Invalid period '{period}'. "
                f"Use one of: {allowed}."
            )

        # Define the date range associated with each
        # supported reporting period.

        ranges = {
            "this_month": (
                "2026-08-01",
                "2026-08-22",
            ),

            "last_month": (
                "2026-07-01",
                "2026-07-31",
            ),

            "last_30_days": (
                "2026-07-24",
                "2026-08-22",
            ),

            "year_to_date": (
                "2026-01-01",
                "2026-08-22",
            ),
        }

        # Select the date range corresponding to the
        # normalized period.
        start, end = ranges[normalized]

        # Open the database in read-only mode.
        with open_read_only_database(
            self.database_path
        ) as connection:

            # Find total expenses grouped by category.
      
            rows = connection.execute(
                """
                SELECT
                    category,
                    -SUM(amount_paise) AS total_paise
                FROM transactions
                WHERE
                    transaction_type = 'expense'
                    AND posted_on BETWEEN ? AND ?
                GROUP BY category
                ORDER BY
                    total_paise DESC,
                    category ASC
                """,
                (
                    start,
                    end,
                ),
            ).fetchall()

        # Convert each database row into a clean dictionary.
        categories = [
            {
                "category": row["category"],
                "amount": self._money(
                    row["total_paise"]
                ),
            }

            for row in rows
        ]

        # Return the complete expense report.
        return {
            "period": normalized,
            "start_date": start,
            "end_date": end,
            "categories": categories,

            # Sum all category totals to get overall spending.
            "total_expenses": round(
                sum(
                    item["amount"]
                    for item in categories
                ),
                2,
            ),

            "currency": "USD",
            "data_as_of": DATA_AS_OF,
        }

    def get_stock_quote(
        self,
        ticker: str,
    ) -> dict[str, object]:

        # Delegate the stock lookup to the quote provider.

        return self.quote_provider.get_quote(
            ticker
        )

