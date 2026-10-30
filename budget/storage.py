"""PostgreSQL storage for transactions, category budgets and settings.

The connection comes from the DATABASE_URL environment variable (or a `.env`
file in the project root), e.g.
    postgresql+psycopg://postgres:secret@localhost:5432/family_budget
Any SQLAlchemy URL works; the tests pass a SQLite file path instead.

Transactions live in an encrypted, tamper-evident ledger (see crypto.py):
each row holds every transaction detail as one AES-256-GCM ciphertext, chained
to the previous row by SHA-256 and signed with Ed25519. Only the id, the time it
was stored and the integrity fields are readable in the database.

  core         immutable details: date, description, amount, type, member,
               channel (manual / csv / sms / demo) and the raw SMS if any.
               Part of the hash chain.
  annotations  what the family can change later: category, source, necessity.
               Separately encrypted, bound to the row's record_hash, so they
               can be edited without breaking the chain.
Deleting a transaction erases its ciphertext but keeps its hashes, so the
chain still verifies ("redaction").
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from cryptography.exceptions import InvalidTag
from sqlalchemy import (Boolean, CheckConstraint, Column, Float, Integer, MetaData, String, Table, Text,
                        create_engine, inspect, select, text)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError

from .crypto import GENESIS_HASH, KEY_VERSION, Vault, chain_hash, sha256_hex

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/family_budget"
ENV_FILE = ROOT / ".env"

metadata = MetaData()
ledger_table = Table(
    "ledger", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", String(32), nullable=False),        # UTC ISO time the row was stored
    Column("key_version", Integer, nullable=False),
    Column("nonce", String(24)),
    Column("ciphertext", Text),                               # NULL once deleted (redacted)
    Column("content_hash", String(64), nullable=False),      # SHA-256 of nonce + ciphertext
    Column("prev_hash", String(64), nullable=False),
    Column("record_hash", String(64), nullable=False, unique=True),
    Column("signature", String(100), nullable=False),        # Ed25519 over record_hash
    Column("annot_nonce", String(24)),
    Column("annot_ciphertext", Text),
    Column("dedupe_tag", String(64), unique=True),           # HMAC of an SMS, NULL for other entries
    Column("deleted", Boolean, nullable=False, default=False),
)
ledger_head_table = Table(
    "ledger_head", metadata,
    Column("id", Integer, primary_key=True),
    Column("record_hash", String(64), nullable=False),
)
budgets_table = Table(
    "budgets", metadata,
    Column("category", String(64), primary_key=True),
    Column("monthly_limit", Float, nullable=False),
    CheckConstraint("monthly_limit >= 0", name="ck_limit_nonnegative"),
)
plans_table = Table(
    "plans", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(80), nullable=False),
    Column("start_date", String(10), nullable=False),        # YYYY-MM-DD, inclusive
    Column("end_date", String(10), nullable=False),          # YYYY-MM-DD, inclusive
    Column("target_total", Float, nullable=False),           # spending ceiling for the whole period
    Column("items", Text, nullable=False, default="[]"),     # JSON: [{"category", "amount", "note"}] planned expenses
    Column("created_at", String(32), nullable=False),
    CheckConstraint("target_total >= 0", name="ck_plan_target_nonnegative"),
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
CORE_AAD = "family-budget/txn-core"
EMPTY_COLUMNS = ["id", "date", "description", "amount", "type", "category", "member", "source", "necessity",
                 "channel"]


class DuplicateTransaction(Exception):
    """The same SMS was already stored."""


def load_dotenv(path: Path = ENV_FILE):
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


def vault_from_env(env_file: Path = ENV_FILE) -> Vault:
    """Keys from the environment / .env; generated and appended to .env on first run."""
    load_dotenv(env_file)
    master, signing = os.environ.get("LEDGER_KEY"), os.environ.get("LEDGER_SIGNING_KEY")
    if master and signing:
        return Vault.from_strings(master, signing)
    vault = Vault.generate()
    keys = vault.export()
    with env_file.open("a", encoding="utf-8") as f:
        f.write("\n# Encryption + signing keys for the transaction ledger. Generated automatically.\n"
                "# BACK THESE UP: without them the stored transactions can't be decrypted.\n")
        for k, v in keys.items():
            f.write(f"{k}={v}\n")
    os.environ.update(keys)
    print(f"Generated new ledger keys and saved them to {env_file}. Back this file up.")
    return vault


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
    def __init__(self, url: str | Path | None = None, vault: Vault | None = None):
        """url: a SQLAlchemy database URL, a path to a SQLite file, or None for DATABASE_URL.
        vault: encryption keys; defaults to .env keys for DATABASE_URL, or fresh keys for an explicit url."""
        if url is None:
            url = database_url()
            vault = vault or vault_from_env()
        elif isinstance(url, Path) or "://" not in str(url):
            Path(url).parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{Path(url).as_posix()}"
        self.vault = vault or Vault.generate()
        self._write_lock = threading.Lock()
        ensure_database(url)
        self.engine: Engine = create_engine(url, pool_pre_ping=True)
        metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(text("INSERT INTO settings (key, value) VALUES (:k, :v) ON CONFLICT (key) DO NOTHING"),
                             {"k": key, "v": value})
            conn.execute(text("INSERT INTO ledger_head (id, record_hash) VALUES (1, :h) ON CONFLICT (id) DO NOTHING"),
                         {"h": GENESIS_HASH})
        self.legacy_rows = self._legacy_row_count()

    def _legacy_row_count(self) -> int:
        """Rows left in the old plaintext `transactions` table (see scripts/encrypt_legacy.py)."""
        if not inspect(self.engine).has_table("transactions"):
            return 0
        with self.engine.connect() as conn:
            return int(conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar())

    # ---- writing the ledger -------------------------------------------
    def _append(self, entries: list[tuple[dict, dict, str | None]]) -> list[int]:
        """entries: [(core, annotations, dedupe_tag)] -> new ids. One DB transaction, chained in order."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ids = []
        with self._write_lock, self.engine.begin() as conn:
            head = conn.execute(select(ledger_head_table.c.record_hash).where(ledger_head_table.c.id == 1)
                                .with_for_update()).scalar_one()
            for core, annotations, tag in entries:
                nonce, ct = self.vault.encrypt(core, CORE_AAD)
                content_hash = sha256_hex(f"{nonce}|{ct}".encode())
                record_hash = chain_hash(head, content_hash, KEY_VERSION)
                a_nonce, a_ct = self.vault.encrypt(annotations, record_hash)
                ids.append(conn.execute(ledger_table.insert().returning(ledger_table.c.id), {
                    "created_at": now, "key_version": KEY_VERSION, "nonce": nonce, "ciphertext": ct,
                    "content_hash": content_hash, "prev_hash": head, "record_hash": record_hash,
                    "signature": self.vault.sign(record_hash), "annot_nonce": a_nonce, "annot_ciphertext": a_ct,
                    "dedupe_tag": tag, "deleted": False,
                }).scalar_one())
                head = record_hash
            conn.execute(ledger_head_table.update().where(ledger_head_table.c.id == 1).values(record_hash=head))
        return ids

    @staticmethod
    def _split(row: dict, channel: str) -> tuple[dict, dict]:
        core = {"date": str(row["date"]), "description": str(row["description"]).strip(),
                "amount": float(row["amount"]), "type": row["type"], "member": str(row.get("member") or "Family"),
                "channel": channel}
        if row.get("sms"):
            core["sms"] = row["sms"]
        annotations = {"category": row["category"], "source": row.get("source", "manual"),
                       "necessity": row.get("necessity") or None}
        return core, annotations

    @staticmethod
    def _check(row: dict):
        if float(row["amount"]) <= 0:
            raise ValueError("amount must be > 0")
        if row["type"] not in ("income", "expense"):
            raise ValueError("type must be income or expense")

    def add_transaction(self, date, description, amount, type_, category,
                        member="Family", source="manual", channel="manual", sms: dict | None = None,
                        dedupe_text: str | None = None) -> int:
        row = {"date": date, "description": description, "amount": amount, "type": type_, "category": category,
               "member": member, "source": source, "sms": sms}
        self._check(row)
        tag = self.vault.mac(dedupe_text) if dedupe_text else None
        if tag and self.is_duplicate(dedupe_text):
            raise DuplicateTransaction("This SMS was already recorded.")
        try:
            return self._append([(*self._split(row, channel), tag)])[0]
        except IntegrityError as e:   # the same SMS arrived twice at the same moment
            raise DuplicateTransaction("This SMS was already recorded.") from e

    def is_duplicate(self, dedupe_text: str) -> bool:
        tag = self.vault.mac(dedupe_text)
        with self.engine.connect() as conn:
            return conn.execute(select(ledger_table.c.id).where(ledger_table.c.dedupe_tag == tag)).first() is not None

    def add_many(self, rows: list[dict], channel: str | None = None) -> int:
        """rows: dicts with TXN_COLUMNS (+ optional necessity). channel defaults to the row's source."""
        for r in rows:
            self._check(r)
        self._append([(*self._split(r, channel or r.get("source", "manual")), None) for r in rows])
        return len(rows)

    def _update_annotations(self, txn_id: int, changes: dict) -> bool:
        with self._write_lock, self.engine.begin() as conn:
            row = conn.execute(select(ledger_table).where(ledger_table.c.id == txn_id,
                                                           ledger_table.c.deleted.is_(False))).mappings().first()
            if row is None:
                return False
            annotations = self.vault.decrypt(row["annot_nonce"], row["annot_ciphertext"], row["record_hash"])
            annotations.update(changes)
            nonce, ct = self.vault.encrypt(annotations, row["record_hash"])
            conn.execute(ledger_table.update().where(ledger_table.c.id == txn_id)
                         .values(annot_nonce=nonce, annot_ciphertext=ct))
        return True

    def update_category(self, txn_id: int, category: str, source="manual") -> bool:
        return self._update_annotations(txn_id, {"category": category, "source": source})

    def set_necessity(self, txn_id: int, label: str | None) -> bool:
        return self._update_annotations(txn_id, {"necessity": label or None})

    def delete_transaction(self, txn_id: int) -> bool:
        """Redact: erase the encrypted details but keep the hashes so the chain still verifies."""
        with self._write_lock, self.engine.begin() as conn:
            return conn.execute(
                ledger_table.update().where(ledger_table.c.id == txn_id, ledger_table.c.deleted.is_(False))
                .values(deleted=True, nonce=None, ciphertext=None, annot_nonce=None, annot_ciphertext=None)
            ).rowcount > 0

    def clear_transactions(self):
        """Start a new, empty ledger (resets the chain to the genesis hash)."""
        with self._write_lock, self.engine.begin() as conn:
            conn.execute(ledger_table.delete())
            conn.execute(ledger_head_table.update().where(ledger_head_table.c.id == 1)
                         .values(record_hash=GENESIS_HASH))

    # ---- reading --------------------------------------------------------
    def _decrypted_rows(self) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(ledger_table).where(ledger_table.c.deleted.is_(False))
                                .order_by(ledger_table.c.id)).mappings().all()
        out, self.unreadable_ids = [], []
        for r in rows:
            try:
                core = self.vault.decrypt(r["nonce"], r["ciphertext"], CORE_AAD)
                annotations = self.vault.decrypt(r["annot_nonce"], r["annot_ciphertext"], r["record_hash"])
            except (InvalidTag, TypeError, ValueError):
                self.unreadable_ids.append(r["id"])    # tampered or wrong key - reported by verify_integrity()
                continue
            out.append({"id": r["id"], **core, **annotations})
        return out

    def transactions(self) -> pd.DataFrame:
        rows = self._decrypted_rows()
        if not rows:
            return pd.DataFrame(columns=EMPTY_COLUMNS)
        df = pd.DataFrame(rows)
        df = df.drop(columns=[c for c in ("sms",) if c in df.columns])
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.strftime("%Y-%m")
        df["amount"] = df["amount"].astype(float)
        return df.sort_values(["date", "id"], ascending=False).reset_index(drop=True)

    def category_corrections(self) -> list[tuple[str, str, str]]:
        """(description, type, category) for every category the family set by hand - k-NN training data."""
        return [(r["description"], r["type"], r["category"]) for r in self._decrypted_rows()
                if r["source"] == "manual"]

    def sms_transactions(self, limit: int = 20) -> list[dict]:
        """Most recent transactions captured from SMS, newest first, including the parsed SMS details."""
        rows = [r for r in self._decrypted_rows() if r.get("channel") == "sms"]
        return rows[::-1][:limit]

    # ---- integrity ------------------------------------------------------
    def verify_integrity(self) -> dict:
        """Recompute the whole chain: content hashes, links, signatures, decryption and the head."""
        with self.engine.connect() as conn:
            rows = conn.execute(select(ledger_table).order_by(ledger_table.c.id)).mappings().all()
            head = conn.execute(select(ledger_head_table.c.record_hash)).scalar_one()
        problems, prev = [], GENESIS_HASH
        for r in rows:
            rid = r["id"]
            if r["prev_hash"] != prev:
                problems.append({"id": rid, "issue": "chain broken: a row before this one was removed or changed"})
            if not r["deleted"]:
                if sha256_hex(f"{r['nonce']}|{r['ciphertext']}".encode()) != r["content_hash"]:
                    problems.append({"id": rid, "issue": "encrypted details were modified"})
                else:
                    try:
                        self.vault.decrypt(r["nonce"], r["ciphertext"], CORE_AAD)
                    except (InvalidTag, TypeError, ValueError):
                        problems.append({"id": rid, "issue": "details can't be decrypted (tampered or wrong key)"})
                try:
                    self.vault.decrypt(r["annot_nonce"], r["annot_ciphertext"], r["record_hash"])
                except (InvalidTag, TypeError, ValueError):
                    problems.append({"id": rid, "issue": "category/label data was modified"})
            if chain_hash(r["prev_hash"], r["content_hash"], r["key_version"]) != r["record_hash"]:
                problems.append({"id": rid, "issue": "record hash doesn't match its contents"})
            if not self.vault.verify_signature(r["record_hash"], r["signature"]):
                problems.append({"id": rid, "issue": "signature invalid"})
            prev = r["record_hash"]
        if head != prev:
            problems.append({"id": None, "issue": "latest rows were removed (chain head doesn't match)"})
        return {"ok": not problems, "rows_checked": len(rows), "deleted": sum(bool(r["deleted"]) for r in rows),
                "head": prev, "problems": problems}

    # ---- budgets ------------------------------------------------------
    def set_budget(self, category: str, monthly_limit: float):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO budgets (category, monthly_limit) VALUES (:c, :l) "
                              "ON CONFLICT (category) DO UPDATE SET monthly_limit = excluded.monthly_limit"),
                         {"c": category, "l": float(monthly_limit)})

    def budgets(self) -> dict[str, float]:
        with self.engine.connect() as conn:
            return {r.category: r.monthly_limit for r in conn.execute(select(budgets_table))}

    # ---- spending plans -----------------------------------------------
    @staticmethod
    def _plan_row(r) -> dict:
        return {"id": r.id, "name": r.name, "start_date": r.start_date, "end_date": r.end_date,
                "target_total": r.target_total, "items": json.loads(r.items or "[]"), "created_at": r.created_at}

    def plans(self) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(plans_table).order_by(plans_table.c.start_date.desc(), plans_table.c.id.desc()))
            return [self._plan_row(r) for r in rows]

    def plan(self, plan_id: int) -> dict | None:
        with self.engine.connect() as conn:
            r = conn.execute(select(plans_table).where(plans_table.c.id == plan_id)).first()
        return self._plan_row(r) if r else None

    def save_plan(self, name: str, start_date, end_date, target_total: float, items: list[dict],
                  plan_id: int | None = None) -> int:
        values = {"name": name.strip(), "start_date": str(start_date), "end_date": str(end_date),
                  "target_total": float(target_total), "items": json.dumps(items)}
        with self.engine.begin() as conn:
            if plan_id is None:
                values["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                return conn.execute(plans_table.insert().returning(plans_table.c.id), values).scalar_one()
            if conn.execute(plans_table.update().where(plans_table.c.id == plan_id).values(**values)).rowcount == 0:
                raise KeyError(plan_id)
            return plan_id

    def delete_plan(self, plan_id: int) -> bool:
        with self.engine.begin() as conn:
            return conn.execute(plans_table.delete().where(plans_table.c.id == plan_id)).rowcount > 0

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
