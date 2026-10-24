"""PostgreSQL storage for transactions, category budgets and settings.

The connection comes from the DATABASE_URL environment variable (or a `.env`
file in the project root), e.g.
    postgresql+psycopg://postgres:secret@localhost:5432/family_budget
Any SQLAlchemy URL works; the tests pass a SQLite file path instead.
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import (CheckConstraint, Column, Float, Integer, MetaData, String, Table, Text, create_engine,
                        insert, select, text)
from sqlalchemy.engine import Engine, make_url

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/family_budget"

metadata = MetaData()
transactions_table = Table(
    "transactions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", String(10), nullable=False),            # YYYY-MM-DD
    Column("description", Text, nullable=False),
    Column("amount", Float, nullable=False),
    Column("type", String(10), nullable=False),
    Column("category", String(64), nullable=False),
    Column("member", String(64), nullable=False, server_default="Family"),
    Column("source", String(16), nullable=False, server_default="manual"),  # manual | knn | demo
    Column("necessity", String(16)),                         # family's own label: Reasonable | Unnecessary | NULL
    CheckConstraint("amount > 0", name="ck_amount_positive"),
    CheckConstraint("type IN ('income', 'expense')", name="ck_type"),
)
budgets_table = Table(
    "budgets", metadata,
    Column("category", String(64), primary_key=True),
    Column("monthly_limit", Float, nullable=False),
    CheckConstraint("monthly_limit >= 0", name="ck_limit_nonnegative"),
)
settings_table = Table(
    "settings", metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),
)

DEFAULT_SETTINGS = {
    "currency": "₹",
    "savings_goal_pct": "20",   # target share of income to save each month
    "family_size": "4",
}
TXN_COLUMNS = ["date", "description", "amount", "type", "category", "member", "source"]


def load_dotenv(path: Path = ROOT / ".env"):
    """Minimal .env reader: KEY=value lines, existing environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def database_url() -> str:
    load_dotenv()
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def ensure_database(url: str):
    """Create the PostgreSQL database named in the URL if it doesn't exist yet."""
    u = make_url(url)
    if not u.get_backend_name().startswith("postgresql") or not u.database:
        return
    admin = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": u.database}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{u.database}"'))
    finally:
        admin.dispose()


class BudgetStore:
    def __init__(self, url: str | Path | None = None):
        """url: a SQLAlchemy database URL, a path to a SQLite file, or None for DATABASE_URL."""
        if url is None:
            url = database_url()
        elif isinstance(url, Path) or "://" not in str(url):
            Path(url).parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{Path(url).as_posix()}"
        ensure_database(url)
        self.engine: Engine = create_engine(url, pool_pre_ping=True)
        metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(text("INSERT INTO settings (key, value) VALUES (:k, :v) ON CONFLICT (key) DO NOTHING"),
                             {"k": key, "v": value})

    # ---- transactions -------------------------------------------------
    def add_transaction(self, date, description, amount, type_, category,
                        member="Family", source="manual") -> int:
        with self.engine.begin() as conn:
            return conn.execute(
                insert(transactions_table).returning(transactions_table.c.id),
                {"date": str(date), "description": description.strip(), "amount": float(amount), "type": type_,
                 "category": category, "member": member, "source": source},
            ).scalar_one()

    def add_many(self, rows: list[dict]) -> int:
        if rows:
            rows = [{c: (float(r[c]) if c == "amount" else str(r[c])) for c in TXN_COLUMNS} for r in rows]
            with self.engine.begin() as conn:
                conn.execute(insert(transactions_table), rows)
        return len(rows)

    def update_category(self, txn_id: int, category: str, source="manual") -> bool:
        with self.engine.begin() as conn:
            return conn.execute(text("UPDATE transactions SET category = :c, source = :s WHERE id = :i"),
                                {"c": category, "s": source, "i": txn_id}).rowcount > 0

    def set_necessity(self, txn_id: int, label: str | None) -> bool:
        with self.engine.begin() as conn:
            return conn.execute(text("UPDATE transactions SET necessity = :n WHERE id = :i"),
                                {"n": label or None, "i": txn_id}).rowcount > 0

    def category_corrections(self) -> list[tuple[str, str, str]]:
        """(description, type, category) for every category the family set by hand - k-NN training data."""
        t = transactions_table.c
        with self.engine.connect() as conn:
            rows = conn.execute(select(t.description, t.type, t.category).where(t.source == "manual")
                                .order_by(t.id)).all()
        return [tuple(r) for r in rows]

    def delete_transaction(self, txn_id: int) -> bool:
        with self.engine.begin() as conn:
            return conn.execute(text("DELETE FROM transactions WHERE id = :i"), {"i": txn_id}).rowcount > 0

    def clear_transactions(self):
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM transactions"))

    def transactions(self) -> pd.DataFrame:
        with self.engine.connect() as conn:
            df = pd.read_sql_query(text("SELECT * FROM transactions ORDER BY date DESC, id DESC"), conn)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df["month"] = df["date"].dt.strftime("%Y-%m")
        return df

    # ---- budgets ------------------------------------------------------
    def set_budget(self, category: str, monthly_limit: float):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO budgets (category, monthly_limit) VALUES (:c, :l) "
                              "ON CONFLICT (category) DO UPDATE SET monthly_limit = excluded.monthly_limit"),
                         {"c": category, "l": float(monthly_limit)})

    def budgets(self) -> dict[str, float]:
        with self.engine.connect() as conn:
            return {r.category: r.monthly_limit for r in conn.execute(select(budgets_table))}

    # ---- settings -----------------------------------------------------
    def get_setting(self, key: str) -> str:
        with self.engine.connect() as conn:
            value = conn.execute(text("SELECT value FROM settings WHERE key = :k"), {"k": key}).scalar()
        return value if value is not None else DEFAULT_SETTINGS.get(key, "")

    def set_setting(self, key: str, value):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO settings (key, value) VALUES (:k, :v) "
                              "ON CONFLICT (key) DO UPDATE SET value = excluded.value"),
                         {"k": key, "v": str(value)})
