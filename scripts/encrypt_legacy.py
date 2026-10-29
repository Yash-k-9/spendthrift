"""Move transactions from the old plaintext `transactions` table into the encrypted ledger.

Earlier versions stored every transaction readable in PostgreSQL. This copies
them (with categories and labels) into the encrypted, signed ledger, verifies
the result, and then drops the plaintext table.

Run from the project root:  python scripts/encrypt_legacy.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from budget.storage import BudgetStore  # noqa: E402


def main():
    store = BudgetStore()
    if not store.legacy_rows:
        print("Nothing to do: no plaintext `transactions` table (or it is empty).")
        return
    with store.engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text("SELECT * FROM transactions ORDER BY id")).mappings()]

    if store.get_setting("legacy_encrypted") != str(len(rows)):   # don't copy twice if run again
        before = len(store.transactions())
        store.add_many(rows)
        after = len(store.transactions())
        report = store.verify_integrity()
        if after - before != len(rows) or not report["ok"]:
            sys.exit(f"Stopped: expected {len(rows)} new encrypted rows, got {after - before}; "
                     f"integrity ok = {report['ok']}. The plaintext table was NOT dropped.")
        store.set_setting("legacy_encrypted", len(rows))

    answer = input(f"Encrypted {len(rows)} transactions and verified the ledger. "
                   "Drop the old plaintext table now? [y/N] ")
    if answer.strip().lower() == "y":
        with store.engine.begin() as conn:
            conn.execute(text("DROP TABLE transactions"))
        print("Dropped the plaintext table. Your transactions now exist only in encrypted form.")
    else:
        print("Kept the plaintext table. Run this again later, or drop it yourself, to finish.")


if __name__ == "__main__":
    main()
