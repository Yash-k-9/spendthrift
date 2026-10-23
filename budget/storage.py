"""SQLite storage for transactions, category budgets and settings."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "budget.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,              -- YYYY-MM-DD
    description TEXT NOT NULL,
    amount      REAL NOT NULL CHECK (amount > 0),
    type        TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    category    TEXT NOT NULL,
    member      TEXT NOT NULL DEFAULT 'Family',
    source      TEXT NOT NULL DEFAULT 'manual', -- manual (family chose) | knn (predicted) | demo
    necessity   TEXT                            -- family's own label: Reasonable | Unnecessary | NULL
);
CREATE TABLE IF NOT EXISTS budgets (
    category      TEXT PRIMARY KEY,
    monthly_limit REAL NOT NULL CHECK (monthly_limit >= 0)
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "currency": "₹",
    "savings_goal_pct": "20",   # target share of income to save each month
    "family_size": "4",
}


class BudgetStore:
    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(transactions)")}
            if "necessity" not in columns:  # databases created by older versions
                conn.execute("ALTER TABLE transactions ADD COLUMN necessity TEXT")
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", (key, value))

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- transactions -------------------------------------------------
    def add_transaction(self, date, description, amount, type_, category,
                        member="Family", source="manual") -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO transactions (date, description, amount, type, category, member, source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(date), description.strip(), float(amount), type_, category, member, source),
            )
            return cur.lastrowid

    def add_many(self, rows: list[dict]) -> int:
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO transactions (date, description, amount, type, category, member, source)"
                " VALUES (:date, :description, :amount, :type, :category, :member, :source)",
                rows,
            )
        return len(rows)

    def update_category(self, txn_id: int, category: str, source="manual") -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE transactions SET category = ?, source = ? WHERE id = ?",
                (category, source, txn_id),
            )
            return cur.rowcount > 0

    def set_necessity(self, txn_id: int, label: str | None) -> bool:
        with self._conn() as conn:
            cur = conn.execute("UPDATE transactions SET necessity = ? WHERE id = ?", (label or None, txn_id))
            return cur.rowcount > 0

    def category_corrections(self) -> list[tuple[str, str, str]]:
        """(description, type, category) for every category the family set by hand - k-NN training data."""
        with self._conn() as conn:
            rows = conn.execute("SELECT description, type, category FROM transactions WHERE source = 'manual'"
                                " ORDER BY id").fetchall()
        return [tuple(r) for r in rows]

    def delete_transaction(self, txn_id: int) -> bool:
        with self._conn() as conn:
            return conn.execute("DELETE FROM transactions WHERE id = ?", (txn_id,)).rowcount > 0

    def clear_transactions(self):
        with self._conn() as conn:
            conn.execute("DELETE FROM transactions")

    def transactions(self) -> pd.DataFrame:
        with self._conn() as conn:
            df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date DESC, id DESC", conn)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df["month"] = df["date"].dt.strftime("%Y-%m")
        return df

    # ---- budgets ------------------------------------------------------
    def set_budget(self, category: str, monthly_limit: float):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO budgets VALUES (?, ?) ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
                (category, float(monthly_limit)),
            )

    def budgets(self) -> dict[str, float]:
        with self._conn() as conn:
            return {r["category"]: r["monthly_limit"] for r in conn.execute("SELECT * FROM budgets")}

    # ---- settings -----------------------------------------------------
    def get_setting(self, key: str) -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else DEFAULT_SETTINGS.get(key, "")

    def set_setting(self, key: str, value):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
