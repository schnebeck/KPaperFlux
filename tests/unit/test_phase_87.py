
import pytest
import json
import uuid
from datetime import date
from core.database import DatabaseManager
from core.document import Document

@pytest.fixture
def db_manager(tmp_path):
    db_path = tmp_path / "test_phase_87.db"
    manager = DatabaseManager(str(db_path))
    manager.init_db()
    
    # Ensure columns exist (if migration needed in runtime vs init)
    # The init_db calls migration logic, so we are good.
    return manager

def test_read_switch_virtual_priority(db_manager):
    """
    Verify that Document reads sender/amount/date from Virtual Columns 
    (semantic_data) if present, overriding legacy columns.
    """
    doc_uuid = str(uuid.uuid4())
    
    # 1. Insert Document with MIXED data
    # Legacy: sender="Legacy Sender"
    # Virtual: semantic_data.summary.sender_name="Virtual Sender"
    
    sql = """
    INSERT INTO documents (uuid, original_filename, sender, semantic_data, created_at)
    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """
    
    semantic_json = json.dumps({
        "summary": {
            "sender_name": "Virtual Sender",
            "amount": "99.99",
            "main_date": "2025-01-01"
        }
    })
    
    with db_manager.connection:
        db_manager.connection.execute(sql, (doc_uuid, "test.pdf", "Legacy Sender", semantic_json))
        
    # 2. Fetch using get_document_by_uuid
    doc = db_manager.get_document_by_uuid(doc_uuid)
    
    print(f"DOC DICT: {doc.dict()}")
    
    assert doc is not None
    # Expectation: Virtual overrides Legacy
    assert doc.sender == "Virtual Sender"
    assert abs(float(doc.amount) - 99.99) < 0.001
    assert str(doc.doc_date) == "2025-01-01"
    
    # Check v_ attributes too
    assert doc.v_sender == "Virtual Sender"
    
def test_read_switch_legacy_fallback(db_manager):
    """
    Verify that Document falls back to Legacy columns if Virtual data is missing.
    """
    doc_uuid = str(uuid.uuid4())
    
    # Insert Document with ONLY Legacy data (semantic_data is NULL)
    sql = """
    INSERT INTO documents (uuid, original_filename, sender, amount, doc_date, created_at)
    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """
    
    with db_manager.connection:
        db_manager.connection.execute(sql, (doc_uuid, "legacy.pdf", "Legacy Fallback", 50.0, "2020-01-01"))
        
    # Fetch
    doc = db_manager.get_document_by_uuid(doc_uuid)
    
    assert doc is not None
    assert doc.sender == "Legacy Fallback"
    assert doc.amount == 50.0
    assert str(doc.doc_date) == "2020-01-01"
    
    assert doc.v_sender is None # Virtual column should be NULL

def test_search_uses_virtual_columns(db_manager):
    """
    Verify search_documents returns Document objects populated from Virtual Columns.
    """
    doc_uuid = str(uuid.uuid4())
    semantic_json = json.dumps({"summary": {"sender_name": "Search Target"}})
    
    with db_manager.connection:
        db_manager.connection.execute(
            "INSERT INTO documents (uuid, original_filename, sender, semantic_data) VALUES (?, ?, ?, ?)",
            (doc_uuid, "search.pdf", "Hidden Legacy", semantic_json)
        )
        
    # Search
    # Note: Text search currently looks at 'text_content', 'filename', 'tags'. 
    # It does NOT look at 'v_sender' yet in the SQL WHERE clause for text search!
    # But the RESULT object should have the correct sender name.
    
    # We cheat and search by filename to find it
    results = db_manager.search_documents("search.pdf")
    assert len(results) == 1
    doc = results[0]
    
    assert doc.sender == "Search Target" # Should result from v_sender
