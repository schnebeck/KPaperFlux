import pytest
from unittest.mock import MagicMock, patch, ANY
import os
from pathlib import Path
from core.pipeline import PipelineProcessor
from core.document import Document
from core.models.physical import PhysicalFile
from core.models.virtual import VirtualDocument
import datetime
import uuid

@pytest.fixture
def mock_vault():
    return MagicMock()

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def pipeline(mock_vault, mock_db):
    # Mock Repositories
    p = PipelineProcessor(vault=mock_vault, db=mock_db)
    p.physical_repo = MagicMock()
    p.logical_repo = MagicMock()
    return p

def test_process_document_success(pipeline, mock_vault, mock_db):
    """
    Test generic process_document flow.
    """
    source_path = "/tmp/fake_scan.pdf"
    
    # Mock Physical Ingestion
    phys_file = PhysicalFile(
         file_uuid=str(uuid.uuid4()),
         original_filename="fake_scan.pdf",
         file_path="/vault/1234.pdf",
         phash="abcd",
         file_size=100,
         page_count=2,
         raw_ocr_data={"1": "Page1", "2": "Page2"},
         ref_count=0,
         created_at=datetime.datetime.now().isoformat()
    )
    pipeline._ingest_physical_file = MagicMock(return_value=phys_file)
    
    # Run
    with patch.object(pipeline, '_run_ai_analysis') as mock_ai:
         with patch.object(pipeline, '_virtual_to_legacy') as mock_v2l:
             legacy_doc = Document(
                 uuid=str(uuid.uuid4()), original_filename="fake_scan.pdf", 
                 created_at=datetime.datetime.now().isoformat()
             )
             mock_v2l.return_value = legacy_doc
             
             result = pipeline.process_document(source_path)
             
             assert result == legacy_doc
             pipeline.logical_repo.save.assert_called()
             mock_ai.assert_called()

def test_reprocess_document_success(pipeline):
    """Test reprocessing an existing V2 entity."""
    entity_id = str(uuid.uuid4())
    
    v_doc = VirtualDocument(
        entity_uuid=entity_id,
        created_at=datetime.datetime.now().isoformat()
    )
    pipeline.logical_repo.get_by_uuid.return_value = v_doc
    
    # Mock Repos for _virtual_to_legacy
    pipeline._run_ai_analysis = MagicMock()
    
    # Needs to fallback to _virtual_to_legacy
    with patch.object(pipeline, '_virtual_to_legacy') as mock_v2l:
        mock_v2l.return_value = Document(uuid=entity_id, original_filename="repro.pdf", created_at=v_doc.created_at)
        
        res = pipeline.reprocess_document(entity_id)
        assert res.uuid == entity_id
        pipeline._run_ai_analysis.assert_called()

def test_pipeline_handles_missing_file(pipeline):
    """Test that pipeline raises error for missing input file."""
    # Ensure ingest throws
    pipeline._ingest_physical_file = MagicMock(side_effect=FileNotFoundError)
    with pytest.raises(FileNotFoundError):
        pipeline.process_document("non_existent.pdf")

# OCR Tests (Mocking subprocess)
@patch("core.pipeline.subprocess.run")
@patch("core.pipeline.tempfile.TemporaryDirectory")
@patch("core.config.AppConfig.get_ocr_binary", return_value="ocrmypdf")
def test_run_ocr_success(mock_get_ocr, mock_temp_dir, mock_run, pipeline, tmp_path):
    """Test successful OCR execution logic."""
    input_file = tmp_path / "test.pdf"
    input_file.touch()
    
    mock_temp_dir.return_value.__enter__.return_value = str(tmp_path)
    
    # The output PDF is what _extract_text_native will read
    output_pdf = tmp_path / f"ocr_{input_file.name}"
    output_pdf.touch()
    
    # We mock _extract_text_native to return dict
    with patch.object(pipeline, '_extract_text_native', return_value={"1": "OCR Text"}):
        res = pipeline._run_ocr(input_file)
        assert res == {"1": "OCR Text"}
        
    mock_run.assert_called()

@patch("core.canonizer.CanonizerService")
def test_pipeline_integration_ai(MockCanonizer, pipeline):
    """Test AI delegation."""
    v_doc = VirtualDocument(entity_uuid="v1", created_at="now")
    
    pipeline._run_ai_analysis(v_doc)
    MockCanonizer.return_value.process_virtual_document.assert_called_with(v_doc)
