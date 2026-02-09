
import pytest
import uuid
from unittest.mock import MagicMock, patch
from core.canonizer import CanonizerService
from core.models.virtual import VirtualDocument, SourceReference
from core.models.semantic import SemanticExtraction

@pytest.fixture
def mock_service():
    db = MagicMock()
    analyzer = MagicMock()
    phys_repo = MagicMock()
    log_repo = MagicMock()
    service = CanonizerService(db, analyzer, phys_repo, log_repo)
    service.config = MagicMock()
    service.config.get_private_profile_json.return_value = None
    service.config.get_business_profile_json.return_value = None
    return service

def test_canonizer_forces_1_to_1_for_protected(mock_service):
    v_doc = VirtualDocument(
        uuid=str(uuid.uuid4()),
        status="NEW",
        is_immutable=True
    )
    # 2 pages in source
    v_doc.source_mapping = [SourceReference(file_uuid="f1", pages=[1, 2])]
    
    # Mock dependencies
    phys_file = MagicMock()
    phys_file.raw_ocr_data = '{"1": "p1", "2": "p2"}'
    mock_service.physical_repo.get_by_uuid.return_value = phys_file

    # Mock analyzer response with a split suggestion (2 entities)
    mock_service.analyzer.run_stage_1_adaptive.return_value = {
        "detected_entities": [
            {"type_tags": ["DOC1"], "page_indices": [1]},
            {"type_tags": ["DOC2"], "page_indices": [2]}
        ]
    }
    
    with patch.object(mock_service, "_atomic_transition", return_value=True):
        with patch.object(mock_service.logical_repo, "save"):
            # Run
            # We wrap in try-except because we didn't mock Stage 2 completely, 
            # but we only care about the state after Stage 1.
            try:
                mock_service.process_virtual_document(v_doc)
            except:
                pass 
            
            # The v_doc should still have 2 pages and the first type tag
            assert len(v_doc.source_mapping[0].pages) == 2
            assert "DOC1" in v_doc.type_tags
            assert "DOC2" not in v_doc.type_tags # DOC2 was discarded as it would involve a split
