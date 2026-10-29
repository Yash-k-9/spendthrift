"""Parse Indian bank transaction SMS into transactions.

Banks word their alerts differently, so parsing is a set of small rules rather
than one template per bank:
  amount      "Rs.450.00", "INR 450", "₹450", or SBI's "debited by 450.0"
  direction   debited / spent / sent / paid / withdrawn  -> expense
              credited / received / deposited            -> income
  merchant    "to VPA swiggy@icici", "trf to SWIGGY", "at AMAZON",
              "UPI/P2M/4298.../SWIGGY", "; SWIGGY credited", "from ACME CORP" ...
  date        24-10-26, 24/10/2026, 24Oct26, 24-Oct-26, 2026-10-24 (else the day received)
  account     last digits after a/c, acct, card
  reference   UPI / Ref No digits
OTP and promotional messages are rejected: only messages with an amount and a
debit/credit direction become transactions.
"""

import re
from datetime import date, datetime

OTP = re.compile(r"\botp\b|one[\s-]?time\s+pass(word|code)|verification code|\bcvv\b", re.I)
AMOUNT = re.compile(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)", re.I)
AMOUNT_AFTER_VERB = re.compile(r"(?:debited|credited)\s+(?:by|with|for)\s+(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)", re.I)
DEBIT = re.compile(r"\b(debited|spent|sent|paid|withdrawn|purchase|debit)\b", re.I)
CREDIT = re.compile(r"\b(credited|received|deposited|credit(?:ed)? to)\b", re.I)
ACCOUNT = re.compile(r"(?:a/c|ac|acct|account|card)\s*(?:no\.?)?\s*[*xX.]*(\d{3,6})\b", re.I)
REFERENCE = re.compile(r"(?:upi/p2[am]/|upi(?:\s*ref)?(?:\s*no)?|ref(?:\s*no)?|refno|rrn)[\s:.#-]*(\d{6,})", re.I)
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
DATES = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b"), "dmy"),
    (re.compile(rf"\b(\d{{1,2}})[-\s]?({MONTHS})[a-z]*[-\s]?(\d{{2,4}})\b", re.I), "dMy"),
]
# Ordered: the first pattern that matches wins.
MERCHANT_PATTERNS = [
    re.compile(r"\bto\s+vpa\s+([\w.\-]+@[\w.\-]+)", re.I),
    re.compile(r"\bby\s+vpa\s+([\w.\-]+@[\w.\-]+)", re.I),
    re.compile(r"\bupi/p2[am]/\d+/(.+?)(?:\s+not you|\s+sms\b|/|$)", re.I),
    re.compile(r"\binfo:?\s*upi[-/]([^/.\n]+?)(?:[-/]|\.|$)", re.I),
    re.compile(r";\s*([A-Za-z0-9 &.'@-]+?)\s+credited", re.I),
    re.compile(r"\btrf\s+to\s+(.+?)\s+(?:ref|on\b|upi)", re.I),
    re.compile(r"\bto\s+([A-Za-z0-9][A-Za-z0-9 &.'@_-]{1,40}?)\s+on\b", re.I),
    re.compile(r"\bat\s+([A-Za-z0-9][A-Za-z0-9 &.'_-]{1,40}?)\s+(?:on\b|\.|ref)", re.I),
    re.compile(r"\b(?:transfer\s+)?from\s+([A-Za-z0-9][A-Za-z0-9 &.'@_-]{1,40}?)\s*(?:\.|ref|on\b|upi|$)", re.I),
    re.compile(r"\bby\s+(neft|imps|rtgs)\b", re.I),
]
NOT_A_MERCHANT = re.compile(r"^(a/?c|ac|acct|account|your|you|card|bank|x+\d*|\d+)$", re.I)


def _amount(body: str) -> float | None:
    m = AMOUNT_AFTER_VERB.search(body) or AMOUNT.search(body)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return value if value > 0 else None


def _type(body: str) -> str | None:
    debit, credit = DEBIT.search(body), CREDIT.search(body)
    if debit and credit:  # e.g. ICICI: "Acct XX123 debited ...; SWIGGY credited" - whichever comes first is ours
        return "expense" if debit.start() < credit.start() else "income"
    return "expense" if debit else "income" if credit else None


def _date(body: str, fallback: date) -> date:
    for pattern, kind in DATES:
        m = pattern.search(body)
        if not m:
            continue
        try:
            if kind == "ymd":
                return date(int(m[1]), int(m[2]), int(m[3]))
            year = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
            if kind == "dmy":
                return date(year, int(m[2]), int(m[1]))
            return datetime.strptime(f"{m[1]} {m[2][:3]} {year}", "%d %b %Y").date()
        except ValueError:
            continue
    return fallback


def _clean_merchant(raw: str) -> str:
    raw = raw.strip(" .:-/")
    if "@" in raw:  # VPA like swiggy.orders@icici -> SWIGGY ORDERS
        raw = raw.split("@")[0]
        raw = re.sub(r"\d{4,}", "", raw)   # phone numbers in personal VPAs
    raw = re.sub(r"[._]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw.upper()


def _merchant(body: str) -> str | None:
    for pattern in MERCHANT_PATTERNS:
        m = pattern.search(body)
        if m:
            name = _clean_merchant(m.group(1))
            if name and not NOT_A_MERCHANT.match(name):
                return name
    return None


def bank_from_sender(sender: str) -> str:
    """'VM-HDFCBK' -> 'HDFCBK' (Indian bank SMS senders are XX-BANKID)."""
    s = sender.strip().upper()
    return s.split("-", 1)[1] if "-" in s else s


def parse(sender: str, body: str, received: datetime | date | None = None) -> dict:
    """Returns {"ok": True, "transaction": {...}} or {"ok": False, "reason": "..."}."""
    body = " ".join((body or "").split())
    received = received or datetime.now()
    received_day = received.date() if isinstance(received, datetime) else received
    if not body:
        return {"ok": False, "reason": "Empty message."}
    if OTP.search(body):
        return {"ok": False, "reason": "Looks like an OTP / security code. Not stored."}
    amount, type_ = _amount(body), _type(body)
    if amount is None or type_ is None:
        return {"ok": False, "reason": "Not a debit/credit alert (no amount or direction found)."}

    merchant = _merchant(body)
    bank = bank_from_sender(sender)
    account = ACCOUNT.search(body)
    ref = REFERENCE.search(body)
    description = merchant or (f"{bank} {'debit' if type_ == 'expense' else 'credit'}")
    return {"ok": True, "transaction": {
        "date": _date(body, received_day).isoformat(),
        "description": description,
        "amount": round(amount, 2),
        "type": type_,
        "bank": bank,
        "account": account.group(1)[-4:] if account else None,
        "reference": ref.group(1) if ref else None,
        "merchant_found": merchant is not None,
    }}


def dedupe_key(sender: str, body: str) -> str:
    """Text identifying one SMS; the store keeps only an HMAC of it."""
    return f"{bank_from_sender(sender)}|{' '.join((body or '').split()).lower()}"
