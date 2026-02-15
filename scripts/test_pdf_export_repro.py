import sys
import os
from PyQt6.QtWidgets import QApplication
from core.exporters.pdf_report import PdfReportGenerator

def test_manual_pdf():
    app = QApplication(sys.argv)
    gen = PdfReportGenerator()
    items = [
        {"type": "text", "value": "Testing reproduction of export issue."},
        {"type": "table", "value": [{"Column 1": "Data 1", "Column 2": "Data 2"}]}
    ]
    try:
        print("Starting PDF generation...")
        metadata = {"id": "test_report", "name": "Tax & Overview", "components": []}
        pdf_bytes = gen.generate("Tax & Overview Report", items, metadata=metadata)
        print(f"Success! Generated {len(pdf_bytes)} bytes.")
        with open("repro_test.pdf", "wb") as f:
            f.write(pdf_bytes)
        print("File saved to repro_test.pdf")
    except Exception as e:
        print(f"FAILED with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_manual_pdf()
