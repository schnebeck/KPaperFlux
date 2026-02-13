from core.utils.zugferd_extractor import ZugferdExtractor
import json
import sys

def check_pdf(path):
    print(f"Checking {path}...")
    data = ZugferdExtractor.extract_from_pdf(path)
    if data:
        print("ZUGFeRD detected!")
        # print(json.dumps(data, indent=2))
    else:
        print("No ZUGFeRD detected.")

if __name__ == "__main__":
    check_pdf("/home/schnebeck/Dokumente/Projects/KPaperFlux/tests/resources/demo_invoices_complex/Demo_13_INVOICE_de.pdf")
    check_pdf("/home/schnebeck/Dokumente/Projects/KPaperFlux/tests/resources/demo_invoices_complex/Demo_01_INVOICE_de.pdf")
