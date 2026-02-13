import unittest
import os
from core.exporters.pdf_report import PdfReportGenerator

class TestPdfReport(unittest.TestCase):
    def test_pdf_generation_smoke(self):
        """Simple smoke test to ensure PDF generation doesn't crash."""
        gen = PdfReportGenerator()
        
        mock_data = {
            "title": "Test Spending Report",
            "table_rows": [
                {"Month": "2024-01", "Amount": 1250.50, "Count": 5},
                {"Month": "2024-02", "Amount": 980.00, "Count": 3}
            ],
            "labels": ["2024-01", "2024-02"],
            "series": [
                {"name": "Total", "data": [1250.50, 980.00]}
            ]
        }
        
        # We don't provide chart images in this basic test
        pdf_bytes = gen.generate(mock_data)
        
        self.assertTrue(len(pdf_bytes) > 100)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        
        # Optional: Save to tmp for manual inspection if needed
        # with open("/tmp/test_report.pdf", "wb") as f: f.write(pdf_bytes)

if __name__ == "__main__":
    unittest.main()
