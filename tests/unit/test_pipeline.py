import pytest
from unittest.mock import MagicMock, patch, ANY
import os
from pathlib import Path
from core.pipeline import PipelineProcessor
from core.models.virtual import VirtualDocument as Document
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
         uuid=str(uuid.uuid4()),
         original_filename="fake_scan.pdf",
         file_path="/vault/1234.pdf",
         phash="abcd",
         file_size=100,
         page_count_phys=2,
         raw_ocr_data={"1": "Page1", "2": "Page2"},
         created_at=datetime.datetime.now().isoformat()
    )
    pipeline._ingest_physical_file = MagicMock(return_value=phys_file)
    
    # Run
    with patch.object(pipeline, '_run_ai_analysis') as mock_ai:
        result = pipeline.process_document(source_path)
         
        assert result is not None
        assert result.original_filename == "fake_scan.pdf"
        pipeline.logical_repo.save.assert_called()
        mock_ai.assert_called()

def test_reprocess_document_success(pipeline):
    """Test reprocessing an existing V2 entity."""
    entity_id = str(uuid.uuid4())
    
    v_doc = VirtualDocument(
        uuid=entity_id,
        created_at=datetime.datetime.now().isoformat()
    )
    pipeline.logical_repo.get_by_uuid.return_value = v_doc
    
    pipeline._run_ai_analysis = MagicMock()
    
    res = pipeline.reprocess_document(entity_id)
    assert res is not None
    assert res.uuid == entity_id
    pipeline._run_ai_analysis.assert_called()

def test_pipeline_handles_missing_file(pipeline):
    """Test that pipeline raises error for missing input file."""
    # Ensure ingest throws
    pipeline._ingest_physical_file = MagicMock(side_effect=FileNotFoundError)
    with pytest.raises(FileNotFoundError):
        pipeline.process_document("non_existent.pdf")

# OCR Tests (Mocking subprocess)
@patch("core.pipeline.subprocess.Popen")
@patch("core.pipeline.tempfile.TemporaryDirectory")
@patch("core.config.AppConfig.get_ocr_binary", return_value="ocrmypdf")
def test_run_ocr_success(mock_get_ocr, mock_temp_dir, mock_popen, pipeline, tmp_path):
    """Test successful OCR execution logic."""
    input_file = tmp_path / "test.pdf"
    input_file.touch()

    # The TemporaryDirectory will return our tmp_path
    mock_temp_dir.return_value.__enter__.return_value = str(tmp_path)
    # The expected output PDF in that temp dir
    output_pdf = tmp_path / f"ocr_{input_file.name}"
    output_pdf.touch()

    # Mock Popen
    mock_process = MagicMock()
    mock_process.poll.return_value = 0
    mock_process.communicate.return_value = (b"", b"")
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    # We mock _extract_text_native to return dict
    with patch.object(pipeline, "_extract_text_native", return_value={"1": "OCR Text"}):
        res = pipeline._run_ocr(input_file)
        assert res == {"1": "OCR Text"}

    mock_popen.assert_called()

@patch("core.canonizer.CanonizerService")
def test_pipeline_integration_ai(MockCanonizer, pipeline):
    """Test AI delegation."""
    v_doc = VirtualDocument(uuid="v1", created_at="now")
    
    pipeline._run_ai_analysis(v_doc)
    MockCanonizer.return_value.process_virtual_document.assert_called_with(v_doc)
