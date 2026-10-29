"""Tests for the encrypted ledger, tamper detection, the bank SMS parser and the SMS API.

Run with:  python -m pytest -q
"""

from datetime import date

import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient
from sqlalchemy import text

import api.main as main
from budget import sms, sms_demo
from budget.crypto import Vault
from budget.storage import BudgetStore, DuplicateTransaction

TODAY = date(2026, 10, 28)


@pytest.fixture
def store(tmp_path):
    s = BudgetStore(tmp_path / "ledger.db")
    for i in range(5):
        s.add_transaction(f"2026-10-0{i + 1}", f"Shop {i}", 100 + i, "expense", "Shopping")
    return s


# ---------------------------------------------------------------- encryption & ledger
def test_vault_round_trip_and_tag_check():
    v = Vault.generate()
    nonce, ct = v.encrypt({"amount": 450.0, "description": "SWIGGY"}, "aad")
    assert v.decrypt(nonce, ct, "aad") == {"amount": 450.0, "description": "SWIGGY"}
    with pytest.raises(InvalidTag):
        v.decrypt(nonce, ct, "different-aad")
    with pytest.raises(InvalidTag):
        Vault.generate().decrypt(nonce, ct, "aad")      # wrong key


def test_keys_export_and_reload():
    v = Vault.generate()
    again = Vault.from_strings(**{"master_b64": v.export()["LEDGER_KEY"],
                                  "signing_b64": v.export()["LEDGER_SIGNING_KEY"]})
    nonce, ct = v.encrypt({"x": 1}, "a")
    assert again.decrypt(nonce, ct, "a") == {"x": 1}
    assert again.verify_signature("h", v.sign("h"))


def test_nothing_readable_in_database(store):
    with store.engine.connect() as conn:
        dump = " ".join(str(v) for row in conn.execute(text("SELECT * FROM ledger")) for v in row)
    assert "Shop" not in dump and "Shopping" not in dump and "100.0" not in dump
    assert list(store.transactions()["description"].sort_values()) == [f"Shop {i}" for i in range(5)]


def test_chain_verifies_and_survives_edits_and_deletes(store):
    assert store.verify_integrity()["ok"]
    store.update_category(2, "Groceries")
    store.set_necessity(3, "Unnecessary")
    store.delete_transaction(4)
    report = store.verify_integrity()
    assert report["ok"] and report["deleted"] == 1
    df = store.transactions().set_index("id")
    assert df.loc[2, "category"] == "Groceries" and df.loc[3, "necessity"] == "Unnecessary" and 4 not in df.index


@pytest.mark.parametrize("attack, expected", [
    ("DELETE FROM ledger WHERE id = 2", "chain broken"),
    ("DELETE FROM ledger WHERE id = 5", "head doesn't match"),
    ("UPDATE ledger SET ciphertext = 'AAAA' || substr(ciphertext, 5) WHERE id = 3", "encrypted details were modified"),
    ("UPDATE ledger SET annot_ciphertext = (SELECT annot_ciphertext FROM ledger WHERE id = 1) WHERE id = 2",
     "category/label data was modified"),
    ("UPDATE ledger SET signature = (SELECT signature FROM ledger WHERE id = 1) WHERE id = 2", "signature invalid"),
])
def test_tampering_is_detected(store, attack, expected):
    with store.engine.begin() as conn:
        conn.execute(text(attack))
    report = store.verify_integrity()
    assert not report["ok"]
    assert any(expected in p["issue"] for p in report["problems"])


def test_duplicate_sms_rejected(store):
    store.add_transaction("2026-10-28", "SWIGGY", 450, "expense", "Dining Out", channel="sms", dedupe_text="abc")
    with pytest.raises(DuplicateTransaction):
        store.add_transaction("2026-10-28", "SWIGGY", 450, "expense", "Dining Out", channel="sms", dedupe_text="abc")


# ---------------------------------------------------------------- SMS parser
@pytest.mark.parametrize("sender, body, expected", [
    ("VM-HDFCBK", "Sent Rs.450.00 From HDFC Bank A/C *1234 To SWIGGY On 28/10/26 Ref 429812345678",
     ("expense", 450.0, "SWIGGY", "2026-10-28", "1234", "429812345678")),
    ("JD-SBIINB", "Dear UPI user A/C X1234 debited by 1,250.0 on date 27Oct26 trf to BIGBASKET Refno 429812345679. -SBI",
     ("expense", 1250.0, "BIGBASKET", "2026-10-27", "1234", "429812345679")),
    ("AX-ICICIB", "ICICI Bank Acct XX123 debited for Rs 299.00 on 26-Oct-26; NETFLIX credited. UPI:429812345670.",
     ("expense", 299.0, "NETFLIX", "2026-10-26", "123", "429812345670")),
    ("VK-AXISBK", "INR 2,100.00 debited A/c no. XX1234 25-10-26, 14:22:10 UPI/P2M/429812345671/HP PETROL PUMP Not you?",
     ("expense", 2100.0, "HP PETROL PUMP", "2026-10-25", "1234", "429812345671")),
    ("BZ-KOTAKB", "Sent Rs.180.00 from Kotak Bank AC X1234 to uber.india@axisbank on 24-10-26.UPI Ref 429812345672.",
     ("expense", 180.0, "UBER INDIA", "2026-10-24", "1234", "429812345672")),
    ("VM-HDFCBK", "Rs.2,999.00 spent on HDFC Bank Card x1234 at AMAZON on 2026-10-23:14:22:10. Not you?",
     ("expense", 2999.0, "AMAZON", "2026-10-23", "1234", None)),
    ("JD-SBIINB", "Dear Customer, Your A/C X1234 has been credited by Rs.85,000.00 on 01Oct26 transfer from ACME CORP Ref No 99887766",
     ("income", 85000.0, "ACME CORP", "2026-10-01", "1234", "99887766")),
])
def test_parses_bank_formats(sender, body, expected):
    r = sms.parse(sender, body, TODAY)
    assert r["ok"], r
    t = r["transaction"]
    assert (t["type"], t["amount"], t["description"], t["date"], t["account"], t["reference"]) == expected


@pytest.mark.parametrize("body", [
    "482913 is your OTP for txn of Rs.2,489.00 at AMAZON on HDFC Bank card x1234. Do not share.",
    "Get flat Rs.100 cashback on your next 3 recharges! Use code SAVE100.",
    "Your verification code is 1234",
])
def test_rejects_otp_and_promotions(body):
    assert not sms.parse("VM-HDFCBK", body, TODAY)["ok"]


def test_demo_messages_all_parse():
    msgs = sms_demo.generate(60, today=TODAY, seed=7, include_decoy=False)
    parsed = [sms.parse(m["sender"], m["body"], TODAY) for m in msgs]
    assert all(p["ok"] for p in parsed)
    assert all(p["transaction"]["description"] not in ("", None) for p in parsed)


# ---------------------------------------------------------------- API
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SMS_TOKEN", "test-token")
    main.sms_token.cache_clear()
    s = BudgetStore(tmp_path / "api.db")
    main.app.dependency_overrides[main.get_store] = lambda: s
    yield TestClient(main.app), s
    main.app.dependency_overrides.clear()
    main.sms_token.cache_clear()


SMS = {"sender": "VM-HDFCBK", "body": "Sent Rs.450.00 From HDFC Bank A/C *1234 To SWIGGY On 28/10/26 Ref 429812345678"}


def test_sms_endpoint_needs_token(client):
    c, _ = client
    assert c.post("/api/sms", json=SMS).status_code == 401
    assert c.post("/api/sms", json=SMS, headers={"X-SMS-Token": "wrong"}).status_code == 401


def test_sms_endpoint_stores_categorizes_and_dedupes(client):
    c, store = client
    r = c.post("/api/sms", json=SMS, headers={"X-SMS-Token": "test-token"}).json()
    assert r["stored"] and r["transaction"]["category"] == "Dining Out"
    again = c.post("/api/sms", json=SMS, headers={"X-SMS-Token": "test-token"}).json()
    assert not again["stored"] and "Duplicate" in again["reason"]
    recent = c.get("/api/sms/recent").json()["rows"]
    assert recent[0]["bank"] == "HDFCBK" and recent[0]["body"] == SMS["body"]
    assert store.verify_integrity()["ok"]


def test_demo_mode_and_security_report(client):
    c, _ = client
    res = c.post("/api/sms/demo", params={"count": 5}).json()
    assert res["stored"] == 5 and len(res["results"]) == 6     # + one rejected OTP/promo
    sec = c.get("/api/security").json()
    assert sec["integrity"]["ok"] and sec["integrity"]["rows_checked"] == 5
    assert sec["newest_decrypted"]["channel"] == "sms"
    assert "SWIGGY" not in str(sec["raw_rows"])


def test_parse_preview_does_not_store(client):
    c, store = client
    r = c.post("/api/sms/parse", json=SMS).json()
    assert r["ok"] and not r["transaction"]["duplicate"]
    assert store.transactions().empty


def test_network_lists_sms_url(client):
    c, _ = client
    n = c.get("/api/network").json()
    assert all(u.endswith("/api/sms") for u in n["sms_urls"])
