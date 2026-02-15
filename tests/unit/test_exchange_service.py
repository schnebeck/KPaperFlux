import pytest
import os
import json
from core.exchange import ExchangeService, ExchangePayload

def test_exchange_payload_model():
    data = {"id": "test_report", "name": "Test Report"}
    payload = ExchangePayload(type="report_definition", payload=data)
    
    assert payload.type == "report_definition"
    assert payload.payload["id"] == "test_report"
    assert payload.origin == "KPaperFlux"

def test_exchange_pdf_embedding(tmp_path):
    # 1. Create a dummy PDF bytes (PyMuPDF can create empty docs)
    import fitz
    doc = fitz.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()
    
    # 2. Embed data
    report_data = {"id": "my_custom_report", "name": "Customized View"}
    embedded_pdf = ExchangeService.embed_in_pdf(pdf_bytes, "report_definition", report_data)
    
    assert isinstance(embedded_pdf, bytes)
    
    # 3. Save to disk and extract
    pdf_path = os.path.join(tmp_path, "test_report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(embedded_pdf)
    
    extracted = ExchangeService.extract_from_pdf(pdf_path)
    assert extracted is not None
    assert extracted.type == "report_definition"
    assert extracted.payload["id"] == "my_custom_report"


def test_exchange_standalone_json(tmp_path):
    data = {"filter": {"AND": []}, "name": "Smart List"}
    target = os.path.join(tmp_path, "export.json")
    ExchangeService.save_to_file("smart_list", data, target)
    
    assert os.path.exists(target)
    with open(target, "r") as f:
        stored = json.load(f)
        assert stored["type"] == "smart_list"
        assert stored["payload"]["name"] == "Smart List"
