import pytest
import json
from unittest.mock import MagicMock, patch
from core.canonizer import CanonizerService
from core.models.virtual import VirtualDocument, SourceReference

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_analyzer():
    analyzer = MagicMock()
    analyzer.run_stage_1_adaptive.return_value = {
        "detected_entities": [{"type_tags": ["INVOICE"], "page_indices": [1, 2]}]
    }
    # Mock run_stage_2 to return minimal valid data
    analyzer.run_stage_2.return_value = {
        "meta_header": {"doc_date": "2025-01-01"},
        "bodies": {},
        "repaired_text": "Clean Text"
    }
    analyzer.generate_smart_filename.return_value = "smart_name.pdf"
    return analyzer

@pytest.fixture
def mock_repos(mock_db):
    logical = MagicMock()
    physical = MagicMock()
    return logical, physical

def test_canonizer_filters_stamps_by_page(mock_db, mock_analyzer, mock_repos):
    logical_repo, physical_repo = mock_repos
    service = CanonizerService(mock_db, mock_analyzer, physical_repo=physical_repo, logical_repo=logical_repo)
    
    # Setup VirtualDocument with 2 pages
    v_doc = VirtualDocument(
        uuid="doc-123",
        source_mapping=[SourceReference(file_uuid="phys-1", pages=[1, 2])],
        status="NEW",
        type_tags=["INVOICE"]
    )
    
    # Mock Physical File with OCR 
    mock_phys = MagicMock()
    mock_phys.file_path = "/tmp/phys1.pdf"
    mock_phys.raw_ocr_data = json.dumps({"1": "Page 1 Text", "2": "Page 2 Text", "3": "Page 3 Text"})
    physical_repo.get_by_uuid.return_value = mock_phys
    
    # Mock Visual Auditor directly on the service instance
    with patch.object(service.visual_auditor, 'run_stage_1_5') as mock_run_1_5:
        # Simulate that Stage 1.5 was called and returned stamps
        mock_run_1_5.return_value = {
            "layer_stamps": [
                {"text": "Stamp P1", "page": 1}
            ]
        }
        
        # We also need to mock _atomic_transition to allow processing
        with patch.object(service, '_atomic_transition', return_value=True):
            service.process_virtual_document(v_doc)
            
            # Verify that VisualAuditor was called with correct target_pages
            mock_run_1_5.assert_called_once()
            args, kwargs = mock_run_1_5.call_args
            called_target_pages = kwargs.get("target_pages")
            assert called_target_pages == [1, 2]
            
            # Verify saved semantic data contains the stamp from P1
            logical_repo.save.assert_called()
            # The last save should have the final status and semantic data
            saved_doc = logical_repo.save.call_args[0][0]
            assert saved_doc.status == "PROCESSED"
            assert saved_doc.semantic_data.visual_audit is not None
            stamps = saved_doc.semantic_data.visual_audit.layer_stamps
            assert len(stamps) == 1
            assert stamps[0]["text"] == "Stamp P1"

