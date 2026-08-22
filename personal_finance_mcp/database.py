import sqlite3
from pathlib import Path


DATA_AS_OF = "2026-08-22"
DEFAULT_DATABASE_PATH = Path(__file__).parent / "data" / "personal_finance.db"


def seed_database(database_path: Path = DEFAULT_DATABASE_PATH) -> None:
  
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                account_type TEXT NOT NULL UNIQUE,
                institution TEXT NOT NULL,
                nickname TEXT NOT NULL,
                balance_cents INTEGER NOT NULL,
                currency TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                posted_on TEXT NOT NULL,
                merchant TEXT NOT NULL,
                category TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                transaction_type TEXT NOT NULL CHECK(transaction_type IN ('income', 'expense')),
                description TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY,
                ticker TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                shares REAL NOT NULL,
                price_cents INTEGER NOT NULL,
                cost_basis_cents INTEGER NOT NULL
            );
            """
        )

        has_seed_data = connection.execute(
            "SELECT EXISTS(SELECT 1 FROM accounts)"
        ).fetchone()[0]
        if has_seed_data:
            return

        connection.executemany(
            "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "checking", "Horizon Bank", "Daily Spending", 248_675, "USD"),
                (2, "savings", "Horizon Bank", "Emergency Fund", 1_275_000, "USD"),
                (3, "credit_card", "Northstar Card", "Rewards Visa", -84_230, "USD"),
            ],
        )
        connection.executemany(
            """INSERT INTO transactions
            (account_id, posted_on, merchant, category, amount_cents, transaction_type, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (1, "2026-08-21", "Green Grocer", "Groceries", -8_745, "expense", "Weekly grocery run"),
                (1, "2026-08-20", "Acme Payroll", "Salary", 325_000, "income", "Biweekly salary"),
                (1, "2026-08-19", "Metro Transit", "Transport", -325, "expense", "Train fare"),
                (1, "2026-08-17", "StreamFlix", "Entertainment", -1_599, "expense", "Monthly subscription"),
                (1, "2026-08-14", "Corner Cafe", "Dining", -1_285, "expense", "Coffee and lunch"),
                (2, "2026-08-20", "Scheduled Transfer", "Savings", 50_000, "income", "Automatic savings transfer"),
                (2, "2026-08-01", "Interest Payment", "Interest", 487, "income", "Monthly interest"),
                (3, "2026-08-21", "Green Grocer", "Groceries", -8_745, "expense", "Card purchase"),
                (3, "2026-08-18", "CloudMobile", "Utilities", -5_499, "expense", "Phone plan"),
                (3, "2026-08-12", "Harbor Energy", "Utilities", -12_840, "expense", "Electricity bill"),
                (3, "2026-08-07", "City Pharmacy", "Health", -2_375, "expense", "Prescription"),
                (3, "2026-07-29", "Home Market", "Groceries", -9_120, "expense", "Grocery run"),
                (3, "2026-07-18", "The Reading Room", "Shopping", -3_450, "expense", "Books"),
            ],
        )
        connection.executemany(
            "INSERT INTO holdings VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "AAPL", "Apple Inc.", 12.0, 23_250, 216_000),
                (2, "VTI", "Vanguard Total Stock Market ETF", 18.5, 31_100, 503_000),
                (3, "MSFT", "Microsoft Corporation", 6.0, 45_800, 246_000),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def open_read_only_database(database_path: Path) -> sqlite3.Connection:
    if not database_path.exists():
        raise FileNotFoundError(f"Finance database not found: {database_path}")
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection
