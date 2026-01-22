import pytest
from unittest.mock import MagicMock, patch
from core.canonizer import CanonizerService
from core.models.canonical_entity import DocType, CanonicalEntity

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_analyzer():
    analyzer = MagicMock()
    # Mock extract_canonical_data to return minimal valid data
    analyzer.extract_canonical_data.return_value = {}
    return analyzer

def test_canonizer_filters_stamps_by_page(mock_db, mock_analyzer):
    service = CanonizerService(mock_db, mock_analyzer)
    
    uuid = "doc-123"
    text = "Page 1\fPage 2" # Two pages to match detected entity range
    semantic_data = {}
    
    # Stamps on Page 1 and Page 3
    extra_data = {
        "stamps": [
            {"text": "Stamp P1", "page": 1},
            {"text": "Stamp P3", "page": 3}
        ]
    }
    
    # Mock classify_structure (Fixed)
    mock_analyzer.classify_structure.return_value = {
        "detected_entities": [{"doc_type": "INVOICE", "pages": [1, 2]}]
    }
    
    with patch.object(service, 'save_entity') as mock_save, \
         patch.object(service, '_classify_direction') as mock_classify:
        
        service.process_document(uuid, text, semantic_data, extra_data)
        
        mock_save.assert_called_once()
        entity = mock_save.call_args[0][0] # First arg
        
        assert isinstance(entity, CanonicalEntity)
        assert entity.page_range == [1, 2]
        
        # Verify Stamps
        assert len(entity.stamps) == 1
        assert entity.stamps[0]["text"] == "Stamp P1"
        # Stamp P3 should be excluded because Page 3 is not in entity range [1, 2]
