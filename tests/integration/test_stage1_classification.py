import pytest
import os
import shutil
import tempfile
import json
from unittest.mock import MagicMock
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from core.vault import DocumentVault
from core.canonizer import CanonizerService
from core.ai_analyzer import AIAnalyzer
import pikepdf

def create_dummy_pdf(path, pages=1):
    pdf = pikepdf.Pdf.new()
    for i in range(pages):
        pdf.add_blank_page(page_size=(595, 842))
    pdf.save(path)

@pytest.fixture
def test_stage1_env():
    temp_dir = tempfile.mkdtemp()
    vault_path = os.path.join(temp_dir, "vault")
    db_path = os.path.join(temp_dir, "test.db")
    os.makedirs(vault_path)
    
    db_manager = DatabaseManager(db_path)
    db_manager.init_db()
    vault = DocumentVault(vault_path)
    pipeline = PipelineProcessor(vault=vault, db=db_manager)
    
    # Mock AI Analyzer
    mock_analyzer = MagicMock(spec=AIAnalyzer)
    mock_analyzer.extract_canonical_data.return_value = {"dummy": "data"} 
    mock_analyzer.run_stage_1_adaptive.return_value = {
        "detected_entities": [
            {"type_tags": ["INVOICE"], "direction": "INBOUND", "tenant_context": "BUSINESS"}
        ]
    }
    mock_analyzer.run_stage_2.return_value = {
        "meta_header": {"doc_date": "2023-01-01", "sender": "Amazon"},
        "bodies": {},
        "repaired_text": "Page 1 text\nPage 2 text"
    }
    mock_analyzer.generate_smart_filename.return_value = "2023-01-01__Amazon__Invoice.pdf"
    
    canonizer = CanonizerService(db_manager, analyzer=mock_analyzer)
    # Mock Visual Auditor to avoid non-serializable MagicMocks
    canonizer.visual_auditor.run_stage_1_5 = MagicMock(return_value={
        "audit_summary": {"was_stamp_interference": False, "has_handwriting": False},
        "integrity": {"is_type_match": True, "suggested_types": []}
    })
    
    yield {
        "pipeline": pipeline,
        "db": db_manager,
        "vault": vault,
        "canonizer": canonizer,
        "mock_analyzer": mock_analyzer,
        "temp_dir": temp_dir
    }
    shutil.rmtree(temp_dir)

def test_stage1_background_flow(test_stage1_env):
    pipeline = test_stage1_env["pipeline"]
    db = test_stage1_env["db"]
    canonizer = test_stage1_env["canonizer"]
    temp_dir = test_stage1_env["temp_dir"]
    
    # 1. Ingest a document (it will have READY_FOR_PIPELINE status)
    pdf_path = os.path.join(temp_dir, "invoice.pdf")
    create_dummy_pdf(pdf_path, 2)
    
    # We call process_document with instructions to get READY_FOR_PIPELINE
    instructions = [
        {"pages": [{"file_page_index": 0, "rotation": 0}, {"file_page_index": 1, "rotation": 90}]}
    ]
    uuids = pipeline.process_document_with_instructions(pdf_path, instructions)
    doc_uuid = uuids[0]
    
    # Manually populate raw_ocr_data for the physical file so canonizer can split pages
    doc = db.get_document_by_uuid(doc_uuid)
    mapping = json.loads(doc.extra_data["source_mapping"])
    f_uuid = mapping[0]["file_uuid"]
    
    physical_repo = test_stage1_env["canonizer"].physical_repo
    pf = physical_repo.get_by_uuid(f_uuid)
    pf.raw_ocr_data = {"1": "Page 1 text", "2": "Page 2 text"}
    physical_repo.save(pf)
    
    # Verify initial state
    doc = db.get_document_by_uuid(doc_uuid)
    assert doc.status == "READY_FOR_PIPELINE"
    assert doc.type_tags == []
    
    # 2. Trigger Canonizer (Phase A & B)
    canonizer.process_pending_documents(limit=1)
    
    # 3. Verify Results
    updated_doc = db.get_document_by_uuid(doc_uuid)
    print(f"\n[DEBUG] Updated Doc: {updated_doc}")
    print(f"[DEBUG] Type Tags: {updated_doc.type_tags}")
    
    # Phase A: OCR
    assert updated_doc.cached_full_text == "Page 1 text\nPage 2 text"
    
    # Phase B: Classification
    assert updated_doc.status == "PROCESSED"
    assert "INVOICE" in updated_doc.type_tags
    assert updated_doc.last_processed_at is not None
    
    # Verify AI call was made with correct number of pages
    mock_analyzer = test_stage1_env["mock_analyzer"]
    mock_analyzer.run_stage_1_adaptive.assert_called_once()
    args, _ = mock_analyzer.run_stage_1_adaptive.call_args
    pages_text = args[0]
    assert len(pages_text) == 2
    assert pages_text[0] == "Page 1 text"
    assert pages_text[1] == "Page 2 text"

    print("\n[SUCCESS] Stage 1 Classification Integration Test passed.")
