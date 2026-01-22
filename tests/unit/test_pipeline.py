import pytest
from unittest.mock import MagicMock, patch, ANY
import os
from pathlib import Path
from core.pipeline import PipelineProcessor
from core.document import Document

@pytest.fixture
def mock_vault():
    return MagicMock()

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def pipeline(mock_vault, mock_db):
    return PipelineProcessor(vault=mock_vault, db=mock_db)

def test_process_document_flow(pipeline, mock_vault, mock_db):
    """
    Test that the pipeline orchestrates the flow correctly:
    1. Creates Document
    2. Runs generic "OCR" (mocked internal method)
    3. Runs "AI" (mocked internal method)
    4. Stores in Vault
    5. Stores in DB
    """
    source_path = "/tmp/fake_scan.pdf"
    
    # Mock specific return values to verify flow
    mock_vault.store_document.return_value = "/vault/1234.pdf"
    mock_db.insert_document.return_value = 42
    
    # Run the pipeline
    # We patch the internal methods of the pipeline instance in a real scenario,
    # or rely on dependency injection for OCR/AI. 
    # For now, let's assume methods exist on the class and we patch them.
    
    with patch.object(pipeline, '_run_ocr', return_value="Extracted Text") as mock_ocr, \
         patch.object(pipeline, '_run_ai_analysis') as mock_ai, \
         patch('pathlib.Path.exists', return_value=True):
         
        # Configure AI mock to update the doc object
        # Configure AI mock to update the doc object
        def side_effect_ai(doc, path):
            doc.sender = "AI_Sender"
            
        mock_ai.side_effect = side_effect_ai
         
        result_doc = pipeline.process_document(source_path)
        
        # Verify result
        assert isinstance(result_doc, Document)
        assert result_doc.original_filename == "fake_scan.pdf"
        assert result_doc.text_content == "Extracted Text"
        assert result_doc.sender == "AI_Sender"
        
        # Verify calls
        mock_ocr.assert_called_once()
        # Verify calls
        mock_ocr.assert_called_once()
        # Expect the PATH returned by store_document ("/vault/1234.pdf"), not source_path
        # Note: Code converts string to Path object before passing
        mock_ai.assert_called_once_with(result_doc, Path("/vault/1234.pdf"))
        
        # Verify Vault storage
        mock_vault.store_document.assert_called_once()
        args, _ = mock_vault.store_document.call_args
        assert args[0] == result_doc  # First arg is doc
        assert args[1] == source_path # Second is path
        
        # Verify DB insertion
        assert pipeline.db.insert_document.called

@patch("core.pipeline.subprocess.run")
@patch("core.pipeline.tempfile.TemporaryDirectory")
@patch("core.config.AppConfig.get_ocr_binary", return_value="ocrmypdf")
def test_run_ocr_success(mock_get_ocr, mock_temp_dir, mock_run, pipeline, tmp_path):
    """Test successful OCR execution."""
    # Setup
    input_file = tmp_path / "test.pdf"
    input_file.touch()
    
    # Mock TemporaryDirectory to return a known path (tmp_path)
    # The context manager returns the object yielded by __enter__
    mock_temp_dir.return_value.__enter__.return_value = str(tmp_path)
    
    # Create the expected sidecar file that the code checks for
    sidecar_txt = tmp_path / f"ocr_{input_file.name}.txt"
    sidecar_txt.write_text("Extracted OCR Text", encoding="utf-8")
    
    text = pipeline._run_ocr(input_file)
        
    assert text == "Extracted OCR Text"
    
    # Verify subprocess call
    assert mock_run.called
    args, _ = mock_run.call_args
    command = args[0]
    assert command[0] == "ocrmypdf"
    assert "--sidecar" in command

@patch("core.pipeline.subprocess.run")
def test_run_ocr_failure(mock_run, pipeline, tmp_path):
    """Test OCR failure handling in process_document."""
    mock_run.side_effect = Exception("OCR Failed")
    input_file = tmp_path / "test.pdf"
    input_file.touch()
    
    # We call process_document to ensure the exception is caught and logged
    doc = pipeline.process_document(str(input_file))
    
    assert doc.text_content == ""
    # Ensure other steps continued (e.g., insertion)
    assert pipeline.db.insert_document.called

@patch("core.pipeline.subprocess.run")
def test_pipeline_handles_missing_file(mock_run, pipeline):
    """Test that pipeline raises error for missing input file."""
    with pytest.raises(FileNotFoundError):
        pipeline.process_document("non_existent.pdf")

def test_reprocess_document_success(pipeline):
    """Test reprocessing an existing document."""
    # Setup
    doc = Document(original_filename="reprocess.pdf")
    pipeline.db.get_document_by_uuid.return_value = doc
    # We return a simple string, but later we mock Path on this string
    pipeline.vault.get_file_path.return_value = "/path/to/vault/file.pdf"
    
    # Mock OCR to return new text
    # We must also mock Path for the existence check inside reprocess_document
    with patch("core.pipeline.Path") as MockPath:
        # Configure MockPath instance
        mock_path_instance = MockPath.return_value
        mock_path_instance.exists.return_value = True
        
        # When _run_ocr is called, it takes a Path object (our mock instance)
        with patch.object(pipeline, '_run_ocr', return_value="New OCR Text") as mock_ocr:
            updated_doc = pipeline.reprocess_document(doc.uuid)
            
            # Verify OCR run on the Path object created from the string
            mock_ocr.assert_called()
            
            # Verify document updated
            assert updated_doc.text_content == "New OCR Text"
            
            # Verify DB update called
            pipeline.db.insert_document.assert_called_with(updated_doc)

def test_reprocess_document_not_found(pipeline):
    """Test reprocessing non-existent UUID."""
    pipeline.db.get_document_by_uuid.return_value = None
    
    result = pipeline.reprocess_document("fake-uuid")
    assert result is None

@patch("core.canonizer.CanonizerService")
def test_pipeline_integration_ai(MockCanonizer, pipeline):
    """Test that AI analysis delegates to Canonizer."""
    # Mock OS environ
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}):
        
        # Setup Canonizer Mock
        mock_canonizer_instance = MockCanonizer.return_value
        
        # Reprocess trigger
        doc = Document(original_filename="ai_test.pdf")
        doc.text_content = "Some text to analyze"
        pipeline.db.get_document_by_uuid.return_value = doc
        pipeline.vault.get_file_path.return_value = "/path/to/file.pdf"
        
        # Mock OCR and Path to avoid errors
        with patch.object(pipeline, '_run_ocr', return_value="Some text to analyze"), \
             patch("core.pipeline.Path") as MP:
                
                MP.return_value.exists.return_value = True
                
                pipeline.reprocess_document(doc.uuid)
        
        # Verify Canonizer Initialized with DB
        MockCanonizer.assert_called_with(pipeline.db)
        
        # Verify process_document called
        mock_canonizer_instance.process_document.assert_called_once()
        args = mock_canonizer_instance.process_document.call_args[0]
        # args: (uuid, text_content, file_path=...)
        assert args[0] == doc.uuid
        assert args[1] == "Some text to analyze"
