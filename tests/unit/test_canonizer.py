
import pytest
from unittest.mock import MagicMock, ANY
import json
from core.canonizer import CanonizerService
from core.models.canonical_entity import DocType

class TestCanonizer:
    
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db
        
    @pytest.fixture
    def mock_analyzer(self):
        analyzer = MagicMock()
        return analyzer
        
    def test_process_pending_documents(self, mock_db, mock_analyzer):
        # Setup
        service = CanonizerService(mock_db, mock_analyzer)
        
        # Mock DB returning 1 pending document
        mock_cursor = MagicMock()
        mock_db.connection.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("uuid-123", "Full Text of Document...", '{"raw": "semantics"}')
        ]
        
        # Mock AI Identification: Split into Invoice + DeliveryNote
        mock_analyzer.identify_entities.return_value = [
            {"type": "INVOICE", "pages": [1], "confidence": 0.9},
            {"type": "DELIVERY_NOTE", "pages": [2], "confidence": 0.8}
        ]
        
        # Mock AI Extraction
        mock_analyzer.extract_canonical_data.side_effect = [
            # First call (Invoice)
            {
                "doc_type": "INVOICE",
                "doc_id": "INV-001",
                "doc_date": "2025-01-01",
                "parties": {"sender": {"name": "TestSender"}},
                "specific_data": {"invoice_number": "INV-001"}
            },
            # Second call (Delivery Note)
            {
                "doc_type": "DELIVERY_NOTE",
                "doc_id": "DN-001",
                "parties": {"recipient": {"name": "Me"}},
                "specific_data": {"tracking_number": "TRACK123"}
            }
        ]
        
        # Execute
        service.process_pending_documents()
        
        # Verify
        # 1. DB Query called
        mock_cursor.execute.assert_called()
        
        # 2. AI Identification called
        mock_analyzer.identify_entities.assert_called_with("Full Text of Document...")
        
        # 3. AI Extraction called twice
        assert mock_analyzer.extract_canonical_data.call_count == 2
        mock_analyzer.extract_canonical_data.assert_any_call(DocType.INVOICE, "Full Text of Document...")
        
        # 4. DB Insert called twice (for 2 entities)
        # We check specific calls to connection.execute
        assert mock_db.connection.execute.call_count == 2 
        
        # Check arguments roughly
        args, _ = mock_db.connection.execute.call_args_list[0]
        sql, params = args
        assert "INSERT INTO semantic_entities" in sql
        assert params[1] == "uuid-123" # source_doc_uuid
        assert params[2] == "INVOICE" # doc_type
