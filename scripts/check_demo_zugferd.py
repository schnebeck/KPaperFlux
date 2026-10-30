from core.utils.zugferd_extractor import ZugferdExtractor
import json
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent / "tests/resources/demo_invoices_complex"

def check_pdf(path):
    print(f"Checking {path}...")
    data = ZugferdExtractor.extract_from_pdf(path)
    if data:
        print("ZUGFeRD detected!")
        # print(json.dumps(data, indent=2))
    else:
        print("No ZUGFeRD detected.")

if __name__ == "__main__":
    check_pdf(str(DEMO_DIR / "Demo_13_INVOICE_de.pdf"))
    check_pdf(str(DEMO_DIR / "Demo_01_INVOICE_de.pdf"))
