"""Write sample statement PDFs to samples/ so you can try the PDF import in the app.

Run from the project root:  python scripts/make_sample_statements.py
Needs fpdf2 (in requirements.txt). The SBI-style file's password is demo1234.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from statement_samples import hdfc_style, phonepe_style, sbi_style  # noqa: E402

OUT = ROOT / "samples"


def main():
    OUT.mkdir(exist_ok=True)
    files = {
        "statement_hdfc_style.pdf": hdfc_style()[0],
        "statement_sbi_style_password_demo1234.pdf": sbi_style("demo1234")[0],
        "statement_phonepe_style.pdf": phonepe_style()[0],
    }
    for name, data in files.items():
        (OUT / name).write_bytes(data)
        print(f"wrote samples/{name} ({len(data) // 1024} KB)")


if __name__ == "__main__":
    main()
