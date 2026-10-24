"""Copy data from the old SQLite database (data/budget.db) into PostgreSQL.

Run from the project root:  python scripts/migrate_sqlite.py [path/to/budget.db]
Uses DATABASE_URL (or .env) for the target. Existing transactions in PostgreSQL are kept;
budgets and settings from SQLite overwrite matching rows.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from budget.storage import ROOT, BudgetStore  # noqa: E402


def main(sqlite_path: Path):
    if not sqlite_path.exists():
        sys.exit(f"No SQLite database at {sqlite_path}")
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    store = BudgetStore()

    rows = [dict(r) for r in src.execute("SELECT * FROM transactions ORDER BY id")]
    store.add_many(rows)
    labelled = [r for r in rows if r.get("necessity")]
    if labelled:  # add_many doesn't carry labels; match them up by the new ids
        new = store.transactions().sort_values("id").tail(len(rows))
        for (_, n), r in zip(new.iterrows(), rows):
            if r.get("necessity"):
                store.set_necessity(int(n["id"]), r["necessity"])
    for r in src.execute("SELECT * FROM budgets"):
        store.set_budget(r["category"], r["monthly_limit"])
    for r in src.execute("SELECT * FROM settings"):
        store.set_setting(r["key"], r["value"])
    print(f"Copied {len(rows)} transactions ({len(labelled)} labelled), budgets and settings to {store.engine.url!r}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "budget.db")
