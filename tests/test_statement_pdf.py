"""Tests for importing bank / UPI-app statement PDFs.

Run with:  python -m pytest -q
"""

import pytest
from fastapi.testclient import TestClient

import api.main as main
from budget import statement_pdf as sp
from budget.storage import BudgetStore
from statement_samples import hdfc_style, phonepe_style, sbi_style


def triples(result):
    return [(r["date"], r["amount"], r["type"]) for r in result["rows"]]


# ---------------------------------------------------------------- parsing the three layouts
def test_ruled_table_statement():
    data, expected = hdfc_style()
    r = sp.parse_pdf(data)
    assert r["method"] == "tables" and triples(r) == expected
    assert r["unresolved"] == 0 and r["balance_mismatches"] == 0
    names = [row["description"] for row in r["rows"]]
    assert names[:3] == ["SALARY ACME TECHNOLOGIES PVT LTD", "SWIGGY", "BIGBASKET"]
    assert "ATM CASH WITHDRAWAL" in names


def test_text_statement_uses_running_balance_and_password():
    data, expected = sbi_style("demo1234")
    with pytest.raises(sp.PasswordRequired) as missing:
        sp.parse_pdf(data)
    assert not missing.value.wrong
    with pytest.raises(sp.PasswordRequired) as wrong:
        sp.parse_pdf(data, "nope")
    assert wrong.value.wrong
    r = sp.parse_pdf(data, "demo1234")
    assert r["method"] == "text" and triples(r) == expected
    assert [row["description"] for row in r["rows"]][0] == "SWIGGY"


def test_upi_app_history_ignores_detail_lines():
    data, expected = phonepe_style()
    r = sp.parse_pdf(data)
    assert triples(r) == expected
    assert [row["description"] for row in r["rows"]][:3] == ["Swiggy", "Blinkit", "Rahul Sharma"]


def test_not_a_pdf():
    with pytest.raises(sp.StatementError):
        sp.parse_pdf(b"date,description,amount\n")


# ---------------------------------------------------------------- helpers
@pytest.mark.parametrize("text, expected", [
    ("02/10/26 UPI", "2026-10-02"), ("02-10-2026", "2026-10-02"), ("2026-10-02", "2026-10-02"),
    ("2 Oct 2026", "2026-10-02"), ("02-Oct-26", "2026-10-02"), ("Oct 2, 2026", "2026-10-02"),
    ("12 Sept 2026", "2026-09-12"), ("Opening balance", None),
])
def test_parse_date(text, expected):
    d = sp.parse_date(text)
    assert (d.isoformat() if d else None) == expected


@pytest.mark.parametrize("narration, expected", [
    ("UPI-SWIGGY-swiggy@icici-ICIC0DC0099-429812345601-Payment", "SWIGGY"),
    ("UPI/429812345678/ZOMATO LTD/zomato@hdfcbank/Dinner", "ZOMATO LTD"),
    ("TO TRANSFER-UPI/DR/429812345702/BIGBASKET/UTIB/bigbasket@/Order", "BIGBASKET"),
    ("BY TRANSFER-NEFT*HDFC0000001*N274262299*ACME TECHNOLOGIES", "ACME TECHNOLOGIES"),
    ("NEFT CR-ACME TECHNOLOGIES PVT LTD-SALARY OCT 2026", "SALARY ACME TECHNOLOGIES PVT LTD"),
    ("IMPS-429812345616-PRIYA K-SBIN-XXXXXXX4321-Gift", "PRIYA K"),
    ("ATW-416021XXXXXX1234-S1ANKM12-BANGALORE", "ATM CASH WITHDRAWAL"),
    ("Paid to Swiggy", "Swiggy"),
    ("INTEREST PAID TILL 30-SEP-2026", "INTEREST PAID TILL 30-SEP-2026"),
])
def test_clean_narration(narration, expected):
    assert sp.clean_narration(narration) == expected


# ---------------------------------------------------------------- API
@pytest.fixture
def client(tmp_path):
    s = BudgetStore(tmp_path / "pdf.db")
    main.app.dependency_overrides[main.get_store] = lambda: s
    yield TestClient(main.app), s
    main.app.dependency_overrides.clear()


def upload(c, data, name="statement.pdf", password=None):
    return c.post("/api/import/preview", files={"file": (name, data, "application/pdf")},
                  data={"password": password} if password else None)


def test_pdf_preview_import_and_duplicates(client):
    c, store = client
    data, expected = hdfc_style()
    res = upload(c, data).json()
    assert res["format"] == "pdf" and len(res["rows"]) == len(expected) and res["duplicates"] == 0
    assert {r["category"] for r in res["rows"] if r["description"] == "SWIGGY"} == {"Dining Out"}
    keep = ("date", "description", "amount", "type", "category", "member", "source")
    assert c.post("/api/import", json=[{k: r[k] for k in keep} for r in res["rows"]]).json()["added"] == len(expected)
    assert len(store.transactions()) == len(expected) and store.verify_integrity()["ok"]

    again = upload(c, data).json()
    assert again["duplicates"] == len(expected) and all(r["duplicate"] for r in again["rows"])


def test_password_flow(client):
    c, _ = client
    data, expected = sbi_style("demo1234")
    first = upload(c, data).json()
    assert first["password_required"] and not first["wrong_password"]
    assert upload(c, data, password="wrong").json()["wrong_password"]
    assert len(upload(c, data, password="demo1234").json()["rows"]) == len(expected)


def test_bad_file_is_rejected(client):
    c, _ = client
    assert upload(c, b"%PDF-1.4 broken", name="x.pdf").status_code == 400
