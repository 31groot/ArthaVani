import sqlite3
from pathlib import Path



# Build the default path for the SQLite database.

DEFAULT_DATABASE_PATH = (
    Path(__file__).parent
    / "data"
    / "personal_finance.db"
)


def seed_database(
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> None:

    # Make sure the directory containing the database exists.


    # parents=True:
    #     create missing parent directories recursively
    #
    # exist_ok=True:
    #     do not raise an error if the directory already exists
    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Open a connection to the SQLite database.
    #
    # If the database file does not exist, SQLite will create it.
    
    connection = sqlite3.connect(database_path)

    try:

        # Execute several SQL statements at once.
        #
        # executescript() is useful here because we need to
        # create multiple tables.
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                account_type TEXT NOT NULL UNIQUE,
                institution TEXT NOT NULL,
                nickname TEXT NOT NULL,
                balance_paise INTEGER NOT NULL,
                currency TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                posted_on TEXT NOT NULL,
                merchant TEXT NOT NULL,
                category TEXT NOT NULL,
                amount_paise INTEGER NOT NULL,
                transaction_type TEXT NOT NULL
                    CHECK(
                        transaction_type
                        IN ('income', 'expense')
                    ),
                description TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY,
                ticker TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                shares REAL NOT NULL,
                price_paise INTEGER NOT NULL,
                cost_basis_paise INTEGER NOT NULL
            );
            """
        )

        # Check whether the accounts table already contains
        # at least one row.
        #
        # SELECT EXISTS(...)
        # returns:
        #
        #     1 → at least one account exists
        #     0 → no accounts exist
        #
        # fetchone()[0]
        # gets that single returned value.
        has_seed_data = connection.execute(
            "SELECT EXISTS(SELECT 1 FROM accounts)"
        ).fetchone()[0]

        # If data already exists, do not insert the demo data again.
  
        if has_seed_data:
            return

        # Insert the initial demo bank/credit-card accounts.
        #
        # ? placeholders are used instead of manually constructing
        # SQL strings.
        #
        # Each tuple in the list represents one database row.
        #
        # Values:
        #
        #     id
        #     account_type
        #     institution
        #     nickname
        #     balance_paise
        #     currency
        #
        # Money is stored as integer paise instead of float rupees.
 
        connection.executemany(
            "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    1,
                    "checking",
                    " HorizonBank",
                    "Daily Spending",
                    248_675,
                    "INR",
                ),
                (
                    2,
                    "savings",
                    "Horizon Bank",
                    "Emergency Fund",
                    1_275_000,
                    "INR",
                ),
                (
                    3,
                    "credit_card",
                    "Northstar Card",
                    "Rewards Visa",
                    -84_230,
                    "INR",
                ),
            ],
        )

        # Insert transaction history.
        #
        # executemany() runs the same INSERT statement for
        # each tuple in the list.

        connection.executemany(
            """
            INSERT INTO transactions
            (
                account_id,
                posted_on,
                merchant,
                category,
                amount_paise,
                transaction_type,
                description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    1,
                    "2026-08-21",
                    "Green Grocer",
                    "Groceries",
                    -8_745,
                    "expense",
                    "Weekly grocery run",
                ),
                (
                    1,
                    "2026-08-20",
                    "Acme Payroll",
                    "Salary",
                    325_000,
                    "income",
                    "Biweekly salary",
                ),
                (
                    1,
                    "2026-08-19",
                    "Metro Transit",
                    "Transport",
                    -325,
                    "expense",
                    "Train fare",
                ),
                (
                    1,
                    "2026-08-17",
                    "StreamFlix",
                    "Entertainment",
                    -1_599,
                    "expense",
                    "Monthly subscription",
                ),
                (
                    1,
                    "2026-08-14",
                    "Corner Cafe",
                    "Dining",
                    -1_285,
                    "expense",
                    "Coffee and lunch",
                ),
                (
                    2,
                    "2026-08-20",
                    "Scheduled Transfer",
                    "Savings",
                    50_000,
                    "income",
                    "Automatic savings transfer",
                ),
                (
                    2,
                    "2026-08-01",
                    "Interest Payment",
                    "Interest",
                    487,
                    "income",
                    "Monthly interest",
                ),
                (
                    3,
                    "2026-08-21",
                    "Green Grocer",
                    "Groceries",
                    -8_745,
                    "expense",
                    "Card purchase",
                ),
                (
                    3,
                    "2026-08-18",
                    "CloudMobile",
                    "Utilities",
                    -5_499,
                    "expense",
                    "Phone plan",
                ),
                (
                    3,
                    "2026-08-12",
                    "Harbor Energy",
                    "Utilities",
                    -12_840,
                    "expense",
                    "Electricity bill",
                ),
                (
                    3,
                    "2026-08-07",
                    "City Pharmacy",
                    "Health",
                    -2_375,
                    "expense",
                    "Prescription",
                ),
                (
                    3,
                    "2026-07-29",
                    "Home Market",
                    "Groceries",
                    -9_120,
                    "expense",
                    "Grocery run",
                ),
                (
                    3,
                    "2026-07-18",
                    "The Reading Room",
                    "Shopping",
                    -3_450,
                    "expense",
                    "Books",
                ),
            ],
        )

        # Insert investment holdings.

        connection.executemany(
            "INSERT INTO holdings VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    1,
                    "RELIANCE",
                    "Reliance Industries Ltd.",
                    12.0,
                    138_525,       # ₹1,385.25 per share, stored as paise
                    1_440_000,     # ₹14,400.00 total cost basis, stored as paise
                ),
                (
                    2,
                    "TCS",
                    "Tata Consultancy Services Ltd.",
                    18.5,
                    315_075,       # ₹3,150.75 per share, stored as paise
                    5_180_000,     # ₹51,800.00 total cost basis, stored as paise
                ),
                (
                    3,
                    "HDFCBANK",
                    "HDFC Bank Ltd.",
                    20.0,
                    187_550,       # ₹1,875.50 per share, stored as paise
                    3_200_000,     # ₹32,000.00 total cost basis, stored as paise
                ),
            ],
        )


        # Save all INSERT/UPDATE/DELETE changes permanently.

        connection.commit()

    finally:

        #Close the database connection.

        connection.close()


def open_read_only_database(
    database_path: Path,
) -> sqlite3.Connection:

    # Make sure the database file actually exists.
    #
    # This is important because sqlite3.connect() normally creates
    # a new empty database if the file is missing.
    #
    # For a read-only finance query, accidentally creating an
    # empty database would be misleading, so we explicitly reject it.
    if not database_path.exists():

        raise FileNotFoundError(
            f"Finance database not found: {database_path}"
        )

    # Open the existing SQLite database in READ-ONLY mode.

    # mode=ro means: read only

    # uri=True tells sqlite3 to interpret the string as
    # a SQLite URI rather than an ordinary filename.

    connection = sqlite3.connect(
        f"file:{database_path}?mode=ro",
        uri=True,
    )

    # Return rows as sqlite3.Row objects.
    #
 
    connection.row_factory = sqlite3.Row

    # Ask SQLite to treat this connection as query-only.

    connection.execute(
        "PRAGMA query_only = ON"
    )

    # Give the ready-to-use read-only connection back to the caller.
    return connection

