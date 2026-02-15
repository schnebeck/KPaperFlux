import pytest
import os
from core.exporters.pdf_report import PdfReportGenerator
from core.exchange import ExchangeService

def test_pdf_generation_smoke():
    """Simple smoke test to ensure PDF generation doesn't crash."""
    gen = PdfReportGenerator()
    
    render_items = [
        {"type": "text", "value": "Summary of recent spending patterns."},
        {"type": "table", "value": [
            {"Month": "2024-01", "Amount": 1250.50},
            {"Month": "2024-02", "Amount": 980.00}
        ]}
    ]
    
    pdf_bytes = gen.generate("Test Report", render_items)
    
    assert len(pdf_bytes) > 100
    assert pdf_bytes.startswith(b"%PDF")

def test_pdf_generation_with_embedding(tmp_path):
    """Test PDF generation with embedded report definition."""
    gen = PdfReportGenerator()
    
    render_items = [{"type": "text", "value": "Sample analytics"}]
    report_config = {"id": "monthly_perf", "name": "Monthly Performance"}
    
    # Use the new metadata dict API
    pdf_bytes = gen.generate("Embedded Report", render_items, metadata=report_config)
    
    # Save to verify with ExchangeService
    pdf_path = os.path.join(tmp_path, "embedded.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
        
    payload = ExchangeService.extract_from_pdf(pdf_path)
    assert payload is not None
    assert payload.type == "report_definition"
    assert payload.payload["id"] == "monthly_perf"
