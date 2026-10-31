"""Sample statement PDFs in three common layouts, for tests and the demo.

  hdfc_style()     ruled table: Date | Narration | Ref | Value Dt | Withdrawal | Deposit | Closing Balance,
                   two pages with the header repeated, one long narration
  sbi_style()      no table lines, "Balance as on" opening line, single amount column + balance,
                   optionally password-protected
  phonepe_style()  UPI-app history: "Oct 24, 2026  Paid to Swiggy  DEBIT  Rs.450" plus detail lines

Each returns (pdf_bytes, expected) where expected is [(date, amount, type)].
Generated with fpdf2 (core fonts, so "Rs." rather than the rupee sign).
"""

from fpdf import FPDF
from fpdf.enums import XPos, YPos

HDFC_ROWS = [  # date, narration, ref, withdrawal, deposit
    ("01/10/26", "NEFT CR-ACME TECHNOLOGIES PVT LTD-SALARY OCT 2026", "N274262201", None, 85000.00),
    ("02/10/26", "UPI-SWIGGY-swiggy@icici-ICIC0DC0099-429812345601-Payment", "429812345601", 452.00, None),
    ("03/10/26", "UPI-BIGBASKET-bigbasket@axisbank-UTIB0000100-429812345602-Order", "429812345602", 2340.50, None),
    ("04/10/26", "ACH D- HDFC LTD HOME LOAN EMI 0045123", "0045123", 18500.00, None),
    ("05/10/26", "UPI-UBER INDIA-uber.india@axisbank-UTIB0000100-429812345603-Trip", "429812345603", 286.00, None),
    ("06/10/26", "POS 416021XXXXXX1234 AMAZON PAY INDIA", "000000000000", 3499.00, None),
    ("07/10/26", "UPI-NETFLIX-netflix@hdfcbank-HDFC0000001-429812345604-Subscription", "429812345604", 649.00, None),
    ("08/10/26", "UPI-RAHUL SHARMA-rahul.sharma@okaxis-UTIB0000200-429812345605-Rent share", "429812345605", None, 4000.00),
    ("09/10/26", "UPI-ZOMATO-zomato@hdfcbank-HDFC0000001-429812345606-Dinner", "429812345606", 612.00, None),
    ("10/10/26", "BILLPAY BESCOM ELECTRICITY BILL CONSUMER 1234567890 OCT", "BD1010261234", 1870.00, None),
    ("12/10/26", "UPI-APOLLO PHARMACY-apollopharmacy@icici-ICIC0000001-429812345607-Medicines", "429812345607", 845.00, None),
    ("13/10/26", "ATW-416021XXXXXX1234-S1ANKM12-BANGALORE", "000000000123", 2000.00, None),
    ("15/10/26", "UPI-BLINKIT-blinkit.grofers@hdfcbank-HDFC0000001-429812345608-Groceries", "429812345608", 734.00, None),
    ("16/10/26", "UPI-BOOKMYSHOW-bookmyshow@kotak-KKBK0000001-429812345609-Movie", "429812345609", 920.00, None),
    ("18/10/26", "UPI-HP PETROL PUMP-hpcl.fuel@sbi-SBIN0000001-429812345610-Fuel", "429812345610", 2500.00, None),
    ("20/10/26", "INTEREST PAID TILL 30-SEP-2026", "000000000000", None, 312.00),
    ("21/10/26", "UPI-SWIGGY-swiggy@icici-ICIC0DC0099-429812345611-Payment", "429812345611", 389.00, None),
    ("22/10/26", "UPI-MYNTRA-myntra@icici-ICIC0000001-429812345612-Shopping", "429812345612", 2199.00, None),
    ("24/10/26", "UPI-JIO PREPAID-jio.recharge@sbi-SBIN0000001-429812345613-Recharge", "429812345613", 719.00, None),
    ("25/10/26", "UPI-CULT FIT-cultfit@ybl-YESB0000001-429812345614-Membership", "429812345614", 1499.00, None),
    ("27/10/26", "UPI-BIGBASKET-bigbasket@axisbank-UTIB0000100-429812345615-Order", "429812345615", 1890.00, None),
    ("28/10/26", "IMPS-429812345616-PRIYA K-SBIN-XXXXXXX4321-Gift", "429812345616", 1500.00, None),
    ("29/10/26", "UPI-ZOMATO-zomato@hdfcbank-HDFC0000001-429812345617-Lunch", "429812345617", 455.00, None),
    ("30/10/26", "UPI-UBER INDIA-uber.india@axisbank-UTIB0000100-429812345618-Trip", "429812345618", 312.00, None),
]

SBI_ROWS = [  # date, description, ref, amount, type
    ("02 Oct 2026", "TO TRANSFER-UPI/DR/429812345701/SWIGGY/YESB/swiggy@ic/Payment", "429812345701", 450.00, "expense"),
    ("03 Oct 2026", "BY TRANSFER-NEFT*HDFC0000001*N274262299*ACME TECHNOLOGIES", "N274262299", 72000.00, "income"),
    ("05 Oct 2026", "TO TRANSFER-UPI/DR/429812345702/BIGBASKET/UTIB/bigbasket@/Order", "429812345702", 1980.00, "expense"),
    ("09 Oct 2026", "ATM WDL-ATM CASH 1234 MG ROAD BANGALORE", "1234", 3000.00, "expense"),
    ("11 Oct 2026", "TO TRANSFER-UPI/DR/429812345703/NETFLIX/HDFC/netflix@hd/Plan", "429812345703", 199.00, "expense"),
    ("14 Oct 2026", "BY TRANSFER-UPI/CR/429812345704/RAHUL SHARMA/UTIB/rahul@ok/Split", "429812345704", 1250.00, "income"),
    ("19 Oct 2026", "TO TRANSFER-UPI/DR/429812345705/OLA CABS/YESB/olacabs@ybl/Ride", "429812345705", 264.00, "expense"),
    ("23 Oct 2026", "DEBIT-ACHDr NACH LIC OF INDIA PREMIUM", "LIC0099", 2450.00, "expense"),
    ("26 Oct 2026", "TO TRANSFER-UPI/DR/429812345706/APOLLO PHARMACY/ICIC/apollo@ic/Med", "429812345706", 530.00, "expense"),
]

PHONEPE_ROWS = [  # date text, description, type, amount
    ("Oct 24, 2026", "Paid to Swiggy", "DEBIT", 450.00),
    ("Oct 24, 2026", "Paid to Blinkit", "DEBIT", 612.00),
    ("Oct 23, 2026", "Received from Rahul Sharma", "CREDIT", 2000.00),
    ("Oct 22, 2026", "Paid to Uber India", "DEBIT", 238.00),
    ("Oct 21, 2026", "Paid to Jio Prepaid", "DEBIT", 299.00),
    ("Oct 20, 2026", "Paid to Zomato", "DEBIT", 540.00),
    ("Oct 19, 2026", "Paid to BookMyShow", "DEBIT", 760.00),
]

MONTH_NUM = {"Oct": "10"}


def _fmt(x: float) -> str:
    """Indian digit grouping: 1,20,000.00"""
    whole, frac = f"{x:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        whole = f"{head},{tail}"
    return f"{whole}.{frac}"


def hdfc_style() -> tuple[bytes, list]:
    pdf = FPDF(orientation="L")
    pdf.set_auto_page_break(True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "HDFC BANK - Statement of account", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=9)
    pdf.cell(0, 6, "Account No: 50100123451234   Statement From: 01/10/2026 To: 31/10/2026",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    balance, expected, data = 41250.75, [], []
    for d, narration, ref, wd, dep in HDFC_ROWS:
        balance += (dep or 0) - (wd or 0)
        data.append((d, narration, ref, d, _fmt(wd) if wd else "", _fmt(dep) if dep else "", _fmt(balance)))
        dd, mm, yy = d.split("/")
        expected.append((f"20{yy}-{mm}-{dd}", wd or dep, "expense" if wd else "income"))
    header = ("Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance")
    with pdf.table(col_widths=(18, 105, 30, 18, 30, 30, 32), text_align=("LEFT", "LEFT", "LEFT", "LEFT", "RIGHT",
                                                                          "RIGHT", "RIGHT"),
                   repeat_headings=1, line_height=5) as table:
        row = table.row()
        for h in header:
            row.cell(h)
        for values in data:
            row = table.row()
            for v in values:
                row.cell(v)
    return bytes(pdf.output()), expected


def sbi_style(password: str | None = None) -> tuple[bytes, list]:
    pdf = FPDF()
    if password:
        pdf.set_encryption(owner_password="owner-" + password, user_password=password)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "State Bank of India - Account Statement", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=8)
    pdf.cell(0, 5, "Account Number : 00000031234567890", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, "Balance as on 1 Oct 2026 : 35,000.00", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 7)
    cols = (20, 20, 80, 24, 16, 16, 18)
    for w, h in zip(cols, ("Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Debit", "Credit",
                           "Balance")):
        pdf.cell(w, 5, h)
    pdf.ln()
    pdf.set_font("Helvetica", size=7)
    balance, expected = 35000.00, []
    for d, desc, ref, amount, kind in SBI_ROWS:
        balance += amount if kind == "income" else -amount
        for w, v in zip(cols, (d, d, desc[:52], ref, _fmt(amount) if kind == "expense" else "",
                               _fmt(amount) if kind == "income" else "", _fmt(balance))):
            pdf.cell(w, 5, v, align="R" if w in (16, 18) else "L")
        pdf.ln()
        day, mon, year = d.split()
        expected.append((f"{year}-{MONTH_NUM[mon]}-{int(day):02d}", amount, kind))
    pdf.ln(2)
    pdf.cell(0, 5, f"Closing Balance : {_fmt(balance)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output()), expected


def phonepe_style() -> tuple[bytes, list]:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Transaction Statement for 98XXXXXX10", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=8)
    pdf.cell(0, 5, "Oct 19, 2026 - Oct 24, 2026", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 8)
    for w, h in zip((32, 90, 25, 30), ("Date", "Transaction Details", "Type", "Amount")):
        pdf.cell(w, 5, h)
    pdf.ln()
    pdf.set_font("Helvetica", size=8)
    expected = []
    for i, (d, desc, kind, amount) in enumerate(PHONEPE_ROWS):
        pdf.cell(32, 5, d)
        pdf.cell(90, 5, desc)
        pdf.cell(25, 5, kind)
        pdf.cell(30, 5, f"Rs.{_fmt(amount)}")
        pdf.ln()
        pdf.cell(32, 4, f"{9 + i}:{10 + i} pm")
        pdf.cell(90, 4, f"Transaction ID T24102026{i:04d}AB  UTR No. 42981234{i:04d}")
        pdf.ln()
        pdf.cell(32, 4, "")
        pdf.cell(90, 4, "Paid by XXXXXXXX1234" if kind == "DEBIT" else "Credited to XXXXXXXX1234")
        pdf.ln(6)
        mon, day, year = d.replace(",", "").split()
        expected.append((f"{year}-{MONTH_NUM[mon]}-{int(day):02d}", amount,
                         "expense" if kind == "DEBIT" else "income"))
    return bytes(pdf.output()), expected
