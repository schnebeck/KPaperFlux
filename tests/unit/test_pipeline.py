import pytest
from unittest.mock import MagicMock, patch
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
        def side_effect_ai(doc):
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
        mock_ai.assert_called_once_with(result_doc)
        
        # Verify Vault storage
        mock_vault.store_document.assert_called_once()
        args, _ = mock_vault.store_document.call_args
        assert args[0] == result_doc  # First arg is doc
        assert args[1] == source_path # Second is path
        
        # Verify DB insertion
        mock_db.insert_document.assert_called_once_with(result_doc)

def test_pipeline_handles_missing_file(pipeline):
    """Test that pipeline raises error for missing input file."""
    # We might need to mock os.path.exists if the pipeline checks it.
    # Assuming pipeline relies on Vault or internal check.
    # Let's mock os.path.exists to False
    with patch('pathlib.Path.exists', return_value=False):
        with pytest.raises(FileNotFoundError):
            pipeline.process_document("/non/existent.pdf")
