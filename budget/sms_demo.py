"""Realistic fake bank SMS for demo mode.

Each message mimics a real Indian bank alert format, so the demo goes through
exactly the same path as a message forwarded from a phone:
    parse -> k-NN categorize -> encrypt -> hash chain -> sign -> store
"""

import random
from datetime import date, datetime, timedelta

# (vpa or merchant name, typical amount range)
MERCHANTS = [
    ("swiggy@icici", "SWIGGY", (180, 650)),
    ("zomato@hdfcbank", "ZOMATO", (200, 700)),
    ("bigbasket@axisbank", "BIGBASKET", (600, 2800)),
    ("blinkit.grofers@hdfcbank", "BLINKIT", (150, 900)),
    ("uber.india@axisbank", "UBER", (120, 560)),
    ("olacabs@ybl", "OLA CABS", (110, 480)),
    ("netflix@hdfcbank", "NETFLIX", (199, 649)),
    ("amazonpay@apl", "AMAZON", (299, 3500)),
    ("bescom.billdesk@icici", "BESCOM ELECTRICITY", (900, 2600)),
    ("jio.recharge@sbi", "JIO PREPAID", (239, 749)),
    ("apollopharmacy@icici", "APOLLO PHARMACY", (150, 1400)),
    ("bookmyshow@kotak", "BOOKMYSHOW", (250, 1200)),
    ("hpcl.fuel@sbi", "HP PETROL PUMP", (500, 2500)),
]
INCOME = [("ACME TECHNOLOGIES PVT LTD", (78000, 92000), "NEFT"), ("RAHUL SHARMA", (500, 4000), "UPI")]

DEBIT_TEMPLATES = [
    ("VM-HDFCBK", "Sent Rs.{amt} From HDFC Bank A/C *{acct} To {name} On {d:%d/%m/%y} Ref {ref} Not You? Call 18002586161/SMS BLOCK UPI to 7308080808"),
    ("JD-SBIINB", "Dear UPI user A/C X{acct} debited by {amt} on date {d:%d%b%y} trf to {name} Refno {ref}. If not u? call 1800111109. -SBI"),
    ("AX-ICICIB", "ICICI Bank Acct XX{acct3} debited for Rs {amt} on {d:%d-%b-%y}; {name} credited. UPI:{ref}. Call 18002662 for dispute. SMS BLOCK {acct3} to 9215676766."),
    ("VK-AXISBK", "INR {amt} debited A/c no. XX{acct} {d:%d-%m-%y}, {t:%H:%M:%S} UPI/P2M/{ref}/{name} Not you? SMS BLOCKUPI Cust ID to 919951860002 Axis Bank"),
    ("BZ-KOTAKB", "Sent Rs.{amt} from Kotak Bank AC X{acct} to {vpa} on {d:%d-%m-%y}.UPI Ref {ref}. Not you, https://kotak.com/KBANKT/Fraud"),
    ("VM-HDFCBK", "Rs.{amt} spent on HDFC Bank Card x{acct} at {name} on {d:%Y-%m-%d}:{t:%H:%M:%S}. Not you? Call 18002586161"),
]
CREDIT_TEMPLATES = [
    ("VM-HDFCBK", "Update! INR {amt} deposited in HDFC Bank A/c XX{acct} on {d:%d-%b-%y} for {mode}-{name}. Avl bal INR 1,24,500.00"),
    ("JD-SBIINB", "Dear Customer, Your A/C X{acct} has been credited by Rs.{amt} on {d:%d%b%y} transfer from {name} Ref No {ref} -SBI"),
]
DECOY_MESSAGES = [  # must NOT become transactions
    ("VM-HDFCBK", "{otp} is your OTP for txn of Rs.{amt} at AMAZON on HDFC Bank card x{acct}. Valid for 5 mins. Do not share it with anyone."),
    ("AD-PAYTMB", "Get flat Rs.100 cashback on your next 3 recharges! Use code SAVE100. T&C apply."),
]


def _fmt(amount: float) -> str:
    return f"{amount:,.2f}"


def generate(n: int = 6, today: date | None = None, seed: int | None = None, include_decoy: bool = True) -> list[dict]:
    """n fake SMS [{sender, body}] from the last few days; one decoy (OTP or promo) when include_decoy."""
    rng = random.Random(seed)
    today = today or date.today()
    acct = f"{rng.randint(1000, 9999)}"
    out = []
    for i in range(n):
        d = today - timedelta(days=rng.randint(0, 4))
        t = datetime(d.year, d.month, d.day, rng.randint(8, 22), rng.randint(0, 59), rng.randint(0, 59))
        ref = str(rng.randint(10 ** 11, 10 ** 12 - 1))
        if i == n - 1 and n > 2 and rng.random() < 0.6:   # occasionally an income message
            name, (lo, hi), mode = rng.choice(INCOME)
            sender, tpl = rng.choice(CREDIT_TEMPLATES)
            body = tpl.format(amt=_fmt(rng.randint(lo, hi)), acct=acct, d=d, name=name, ref=ref, mode=mode)
        else:
            vpa, name, (lo, hi) = rng.choice(MERCHANTS)
            sender, tpl = rng.choice(DEBIT_TEMPLATES)
            body = tpl.format(amt=_fmt(rng.randint(lo, hi)), acct=acct, acct3=acct[-3:], d=d, t=t, name=name,
                              vpa=vpa, ref=ref)
        out.append({"sender": sender, "body": body})
    if include_decoy:
        sender, tpl = rng.choice(DECOY_MESSAGES)
        out.append({"sender": sender, "body": tpl.format(otp=rng.randint(100000, 999999),
                                                          amt=_fmt(rng.randint(300, 3000)), acct=acct)})
    return out
