import pytest
import os
import json
import sqlite3
from unittest.mock import MagicMock, patch
from core.document import Document
from core.database import DatabaseManager
from core.ai_analyzer import AIAnalyzer, AIAnalysisResult

# Use an in-memory DB or temporary file for testing
TEST_DB = "test_extra.db"

@pytest.fixture
def db_manager():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    db = DatabaseManager(TEST_DB)
    db.init_db()
    yield db
    db.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_extra_data_storage(db_manager):
    """
    Test Step 1-6: Create doc with extra_data, save, load, verify.
    """
    # 1. Create Document with extra_data (Simulating AI Stamp Extraction)
    ai_stamp_data = {
        "stamps": {
            "type": "entry", 
            "cost_center": "100"
        }
    }
    
    doc = Document(
        original_filename="invoice_scan.pdf",
        text_content="Invoice 12345...",
        extra_data=ai_stamp_data 
    )
    
    # 2. Save to DB
    doc_id = db_manager.insert_document(doc)

    # 3. Load from DB
    loaded_doc = db_manager.get_document_by_uuid(doc.uuid)
    
    # 4. Assert
    assert loaded_doc is not None
    assert loaded_doc.extra_data is not None
    assert loaded_doc.extra_data["stamps"]["cost_center"] == "100"

def test_json_filtering(db_manager):
    """
    Test Step 7: Filtering via SQL JSON functions.
    """
    doc1 = Document(original_filename="doc1.pdf", extra_data={"type": "A", "val": 10})
    doc2 = Document(original_filename="doc2.pdf", extra_data={"type": "B", "val": 20})
    doc3 = Document(original_filename="doc3.pdf", extra_data={"type": "A", "val": 30})
    
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    db_manager.insert_document(doc3)
    
    cursor = db_manager.connection.cursor()
    
    # Find all docs with type="A"
    query = "SELECT original_filename FROM documents WHERE json_extract(extra_data, '$.type') = 'A'"
    try:
        cursor.execute(query)
        results = [row[0] for row in cursor.fetchall()]
        
        assert "doc1.pdf" in results
        assert "doc3.pdf" in results
        assert "doc2.pdf" not in results
        
    except sqlite3.OperationalError as e:
         pytest.skip(f"SQLite JSON not supported or syntax error: {e}")

def test_ai_analyzer_stamp_parsing():
    """
    Test if AIAnalyzer correctly parses extra_data/stamps from mocked JSON response.
    """
    analyzer = AIAnalyzer("fake_key")
    
    # Mock Response
    mock_json_response = json.dumps({
        "summary": {
             "doc_type": ["Invoice"],
             "main_date": "2023-01-01"
        },
        "pages": [
            {
                "regions": [
                    {
                        "type": "address",
                        "role": "sender",
                        "structured": {"name": "Test Sender"}
                    }
                ]
            }
        ],
        "extra_data": {
            "stamps": [
                {"type": "entry", "date": "2023-01-02", "user": "admin"}
            ]
        }
    })
    
    # Mock Client
    mock_response_obj = MagicMock()
    mock_response_obj.text = mock_json_response
    
    analyzer.client.models.generate_content = MagicMock(return_value=mock_response_obj)
    
    # Run
    result = analyzer.analyze_text("Some text")
    
    # Assert
    assert result.sender == "Test Sender"
    
    # Phase 90: AIAnalyzer puts everything into 'semantic_data'
    # extra_data property on result might be None, so check semantic_data
    assert result.semantic_data is not None
    assert "extra_data" in result.semantic_data
    assert "stamps" in result.semantic_data["extra_data"]
    assert result.semantic_data["extra_data"]["stamps"][0]["type"] == "entry"
    assert result.semantic_data["extra_data"]["stamps"][0]["user"] == "admin"
