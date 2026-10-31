"""Read transactions from bank / UPI-app statement PDFs.

Statements differ per bank, so parsing works in two passes:

1. Tables. pdfplumber finds ruled tables; the header row is matched against
   known column names (Date / Narration / Withdrawal / Deposit / Balance and
   each bank's variants). Narrations that wrap onto several lines are joined.
   Pages without a header reuse the previous page's columns.
2. Text lines, for PDFs without table borders (e.g. UPI-app statements): every
   line that starts with a date becomes a transaction; amounts are read from
   the end of the line.

Debit vs credit, in order of reliability: separate debit/credit columns; the
change in the running balance; Dr/Cr or DEBIT/CREDIT markers; wording such as
"BY TRANSFER" (credit) or "Paid to" (debit).

Password-protected statements (common for Indian banks) are opened with the
password the user provides.
"""

import io
import re
from datetime import date, datetime

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect

MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
DATE_PATTERNS = [   # (regex, strptime formats tried in order)
    (re.compile(r"^(\d{4}-\d{2}-\d{2})"), ["%Y-%m-%d"]),
    (re.compile(r"^(\d{1,2}[/-]\d{1,2}[/-]\d{4})"), ["%d/%m/%Y", "%d-%m-%Y"]),
    (re.compile(r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2})\b"), ["%d/%m/%y", "%d-%m-%y"]),
    (re.compile(rf"^(\d{{1,2}}[\s/-](?:{MONTHS})[a-z]*[\s/-]\d{{2,4}})", re.I),
     ["%d %b %Y", "%d-%b-%Y", "%d/%b/%Y", "%d %b %y", "%d-%b-%y", "%d %B %Y", "%d-%B-%Y"]),
    (re.compile(rf"^((?:{MONTHS})[a-z]*\s+\d{{1,2}},?\s+\d{{4}})", re.I), ["%b %d, %Y", "%b %d %Y", "%B %d, %Y", "%B %d %Y"]),
]
AMOUNT = re.compile(r"(?<![\w.])(?:rs\.?\s*|inr\s*|₹\s*)?(\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})|\d+\.\d{2})(?:\s*(cr|dr)\b)?",
                    re.I)
SKIP_ROW = re.compile(r"opening\s+balance|closing\s+balance|^\s*total|balance\s+(b/f|c/f|brought|carried)|"
                      r"statement\s+summary|^\s*b/f|^\s*c/f", re.I)
CREDIT_WORDS = re.compile(r"\b(by\s+transfer|by\s+clg|credit(ed)?|received\s+from|deposit|salary|refund|interest\s+paid|"
                          r"cashback|reversal|neft\s+cr|imps\s+cr|upi\s+cr|\bcr\b)", re.I)
OPENING = re.compile(r"opening\s+balance|balance\s+as\s+on|balance\s+b/f|brought\s+forward", re.I)
NOISE = re.compile(r"transaction\s+id|\butr\b|ref(erence)?\s*(no|#|:)|paid\s+by|debited\s+from|credited\s+to|"
                   r"^\d{1,2}:\d{2}|page\s+\d+|statement\s+(of|period|for)|account\s+(no|number)", re.I)
DEBIT_WORDS = re.compile(r"\b(to\s+transfer|paid\s+to|debit(ed)?|withdrawal|atm|purchase|pos\b|bill\s*pay|emi|"
                         r"upi\s+dr|neft\s+dr|imps\s+dr|\bdr\b)", re.I)

HEADER_KEYS = {   # column role -> words that identify it in a header cell
    "date": ["txn date", "tran date", "transaction date", "trans date", "date"],
    "value_date": ["value date", "value dt"],
    "description": ["narration", "description", "particulars", "transaction details", "details", "remarks"],
    "debit": ["withdrawal", "debit", "dr amount", "amount dr", "paid out"],
    "credit": ["deposit", "credit", "cr amount", "amount cr", "paid in"],
    "amount": ["amount", "txn amount", "transaction amount"],
    "type": ["dr/cr", "cr/dr", "type", "txn type"],
    "balance": ["closing balance", "balance"],
    "ref": ["chq", "ref", "cheque"],
}


class StatementError(Exception):
    """The PDF couldn't be read as a statement."""


class PasswordRequired(StatementError):
    def __init__(self, wrong: bool):
        self.wrong = wrong
        super().__init__("Wrong password for this PDF." if wrong else "This PDF is password-protected.")


# ---------------------------------------------------------------- small parsers
def parse_date(text: str) -> date | None:
    text = " ".join((text or "").split())
    for pattern, formats in DATE_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        raw = re.sub(r"\s+", " ", m.group(1)).replace(",", ", ").replace(",  ", ", ")
        for fmt in formats:
            for candidate in (raw, raw.title(), raw.replace("Sept", "Sep").replace("sept", "sep")):
                try:
                    return datetime.strptime(candidate, fmt).date()
                except ValueError:
                    continue
    return None


def parse_amount(text: str) -> float | None:
    m = AMOUNT.search(text or "")
    return float(m.group(1).replace(",", "")) if m else None


CHANNEL_PREFIX = re.compile(  # how banks start a narration before the counterparty's name
    r"^(?:(?:to|by)\s+transfer\s*-\s*)?(?:(?:upi|neft|imps|rtgs)(?:\s*(?:cr|dr))?\s*[-/*]|ach\s*[dc]\s*-|"
    r"pos\s+\S+\s+|billpay\s+|atw-\S+-|debit-)\s*", re.I)
SKIP_PART = re.compile(  # pieces of a narration that aren't the counterparty
    r"(p2[am]|dr|cr|upi|neft|imps|payment|pay|paid|sent|ref|na|\d+|[a-z]{4}0[a-z0-9]{6}|[a-z]{1,2}\d{6,}|x+\d+)",
    re.I)
TRAILING_REF = re.compile(r"(?:\s+(?:\d{4,}|(?=\w*\d{4})\w{6,}))+$")


def clean_narration(text: str) -> str:
    """Narration -> counterparty name, e.g.
    'UPI-SWIGGY-swiggy@icici-ICIC0DC0099-4298...-Payment' -> 'SWIGGY'
    'TO TRANSFER-UPI/DR/4298.../BIGBASKET/UTIB/...'       -> 'BIGBASKET'
    'NEFT CR-ACME TECHNOLOGIES PVT LTD-SALARY OCT 2026'    -> 'ACME TECHNOLOGIES PVT LTD'
    Narrations without a payment-channel prefix are only tidied."""
    text = " ".join((text or "").split())
    if re.search(r"\b(atw|atm\s*wdl|nwd|atm\s+cash|cash\s+withdrawal)\b", text, re.I):
        return "ATM CASH WITHDRAWAL"
    if re.search(r"\bsal(ary)?\b", text, re.I):   # keep "salary" so k-NN files it as Salary
        name = clean_narration(re.sub(r"\bsal(ary)?\b.*$", "", text, flags=re.I).strip(" -/*"))
        return f"SALARY {name}".strip() if name and name.upper() != "SALARY" else "SALARY"
    text = re.sub(r"^(paid\s+to|received\s+from|money\s+sent\s+to)\s+", "", text, flags=re.I)
    m = CHANNEL_PREFIX.match(text)
    if not m:
        return TRAILING_REF.sub("", text)[:120]
    for part in re.split(r"[/*]|-(?!\s)|\s-\s", text[m.end():]):
        part = part.strip()
        if "@" in part:
            part = part.split("@")[0]
        part = TRAILING_REF.sub("", part)
        if not part or SKIP_PART.fullmatch(part):
            continue
        if len(re.sub(r"[^a-z]", "", part, flags=re.I)) >= 3:
            return re.sub(r"[._]+", " ", part).strip().upper()
    return TRAILING_REF.sub("", text)[:120]


def _infer_type(description: str, marker: str | None = None) -> str | None:
    if marker:
        return "income" if marker.lower() in ("cr", "credit") else "expense"
    credit, debit = CREDIT_WORDS.search(description), DEBIT_WORDS.search(description)
    if credit and debit:
        return "income" if credit.start() < debit.start() else "expense"
    return "income" if credit else "expense" if debit else None


# ---------------------------------------------------------------- pass 1: tables
def _map_header(row: list) -> dict | None:
    cells = [" ".join(str(c or "").lower().split()) for c in row]
    roles = {}
    for role, words in HEADER_KEYS.items():
        for i, cell in enumerate(cells):
            if i in roles.values() or not cell:
                continue
            if any(cell == w or cell.startswith(w) or w in cell for w in words):
                if role == "date" and any(v in cell for v in HEADER_KEYS["value_date"]):
                    continue   # "Value Date" is not the transaction date
                if role == "amount" and any(w in cell for w in HEADER_KEYS["debit"] + HEADER_KEYS["credit"]):
                    continue
                roles[role] = i
                break
    has_money = "debit" in roles or "credit" in roles or "amount" in roles or "balance" in roles
    return roles if "date" in roles and "description" in roles and has_money else None


def _rows_from_tables(pdf) -> list[dict]:
    out, mapping, width = [], None, None
    for page in pdf.pages:
        for table in page.extract_tables():
            for row in table:
                if not row or all(c in (None, "") for c in row):
                    continue
                header = _map_header(row)
                if header:
                    mapping, width = header, len(row)
                    continue
                if not mapping or len(row) != width:
                    continue
                cell = lambda role: str(row[mapping[role]] or "").strip() if role in mapping else ""
                desc = cell("description")
                d = parse_date(cell("date"))
                if d is None:
                    if out and desc and not any(cell(r) for r in ("debit", "credit", "amount", "balance")):
                        out[-1]["raw"] += " " + desc      # wrapped narration line
                    continue
                if SKIP_ROW.search(desc):
                    continue
                debit, credit = parse_amount(cell("debit")), parse_amount(cell("credit"))
                amount, marker = None, None
                if debit or credit:
                    amount, kind = (debit, "expense") if debit else (credit, "income")
                else:
                    amount = parse_amount(cell("amount"))
                    m = AMOUNT.search(cell("amount"))
                    marker = (m.group(2) if m and m.group(2) else None) or (cell("type") or None)
                    kind = _infer_type(desc, marker if marker and marker.lower() in ("cr", "dr", "credit", "debit")
                                       else None)
                out.append({"date": d, "raw": desc, "amount": amount, "type": kind if amount else None,
                            "balance": parse_amount(cell("balance"))})
    return out


# ---------------------------------------------------------------- pass 2: text lines
def _rows_from_text(pdf) -> list[dict]:
    out = []
    for page in pdf.pages:
        for line in (page.extract_text() or "").splitlines():
            line = " ".join(line.split())
            if OPENING.search(line) and AMOUNT.search(line):   # starting balance for the balance check
                amounts = list(AMOUNT.finditer(line))
                out.append({"opening": True, "date": None, "raw": "", "amount": None, "type": None,
                            "balance": float(amounts[-1].group(1).replace(",", ""))})
                continue
            d = parse_date(line)
            if d is None:
                if out and not out[-1].get("opening") and line and not AMOUNT.search(line) \
                        and not SKIP_ROW.search(line) and not NOISE.search(line) and len(line) < 80:
                    out[-1]["raw"] += " " + line          # wrapped description
                continue
            rest = _strip_dates(line)
            if SKIP_ROW.search(rest):
                continue
            amounts = list(AMOUNT.finditer(rest))
            if not amounts:
                continue
            first = amounts[0]
            desc = rest[:first.start()].strip(" -|")
            desc = re.sub(r"\b(DEBIT|CREDIT)\b\s*$", "", desc, flags=re.I).strip()
            word = re.search(r"\b(DEBIT|CREDIT)\b", rest, re.I)
            balance = float(amounts[-1].group(1).replace(",", "")) if len(amounts) >= 2 else None
            amount = float(first.group(1).replace(",", ""))
            marker = first.group(2) or (word.group(1) if word else None)
            out.append({"date": d, "raw": desc, "amount": amount, "type": _infer_type(desc, marker),
                        "balance": balance})
    return out


def _strip_dates(line: str) -> str:
    """The line with its leading date (and a second, value date) removed."""
    for _ in range(2):
        for pattern, _formats in DATE_PATTERNS:
            m = pattern.match(line)
            if m and parse_date(m.group(1)):
                line = line[m.end():].strip()
                break
    return line


# ---------------------------------------------------------------- putting it together
def _resolve_with_balance(rows: list[dict]) -> int:
    """Use the running balance to fix/confirm debit vs credit. Returns how many rows didn't reconcile."""
    mismatches = 0
    for prev, row in zip(rows, rows[1:]):
        if prev["balance"] is None or row["balance"] is None or row["amount"] is None:
            continue
        delta = round(row["balance"] - prev["balance"], 2)
        if abs(abs(delta) - row["amount"]) <= 0.05:
            row["type"] = "income" if delta > 0 else "expense"
        elif row["type"] is not None:
            mismatches += 1
    return mismatches


def parse_pdf(data: bytes, password: str | None = None) -> dict:
    """-> {"rows": [{date, description, amount, type}], "method", "pages", "unresolved", "balance_mismatches"}"""
    try:
        pdf = pdfplumber.open(io.BytesIO(data), password=password or "")
    except Exception as e:  # pdfplumber wraps pdfminer's errors, so look inside too
        causes = [e, e.__cause__, *getattr(e, "args", ())]
        if any(isinstance(c, PDFPasswordIncorrect) for c in causes):
            raise PasswordRequired(wrong=bool(password)) from None
        raise StatementError("Couldn't open the file as a PDF. Is it a statement downloaded from your bank?") from e

    with pdf:
        pages = len(pdf.pages)
        rows, method = _rows_from_tables(pdf), "tables"
        if sum(not r.get("opening") for r in rows) < 2:
            rows, method = _rows_from_text(pdf), "text"
        if not rows and not any((p.extract_text() or "").strip() for p in pdf.pages):
            raise StatementError("This PDF has no text layer (it's a scanned image). Download the statement as a "
                                 "digital PDF or CSV from your bank instead.")

    mismatches = _resolve_with_balance(rows)
    out, unresolved = [], 0
    for r in rows:
        if r.get("opening") or not r["amount"] or r["amount"] <= 0:
            continue
        if r["type"] is None:
            unresolved += 1
            r["type"] = "expense"   # safest default; flagged for review
            r["guessed_type"] = True
        out.append({"date": r["date"].isoformat(), "description": clean_narration(r["raw"]) or "Statement entry",
                    "narration": " ".join(r["raw"].split())[:200], "amount": round(r["amount"], 2),
                    "type": r["type"], "type_guessed": bool(r.get("guessed_type"))})
    if not out:
        raise StatementError("No transactions found. Is this a bank or UPI-app statement?")
    return {"rows": out, "method": method, "pages": pages, "unresolved": unresolved,
            "balance_mismatches": mismatches}
