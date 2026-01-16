import pytest
import os
import json
from datetime import datetime
from core.document import Document
from core.database import DatabaseManager

TEST_DB = "test_search.db"

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

def test_search_text(db_manager):
    """Test searching by text content or filename."""
    doc1 = Document(original_filename="contract_alpha.pdf", text_content="This is a secret agreement.")
    doc2 = Document(original_filename="receipt_beta.pdf", text_content="Grocery list: apples, bananas.")
    
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    
    # Search by filename part
    results = db_manager.search_documents(text_query="alpha")
    assert len(results) == 1
    assert results[0].uuid == doc1.uuid
    
    # Search by content
    results = db_manager.search_documents(text_query="apples")
    assert len(results) == 1
    assert results[0].uuid == doc2.uuid
    
    # No match
    results = db_manager.search_documents(text_query="gamma")
    assert len(results) == 0

def test_search_dynamic_json(db_manager):
    """Test searching by JSON fields in extra_data."""
    stamp1 = {"stamps": {"type": "entry", "cost_center": "100"}}
    stamp2 = {"stamps": {"type": "accounting", "cost_center": "200"}}
    
    doc1 = Document(original_filename="doc1.pdf", extra_data=stamp1)
    doc2 = Document(original_filename="doc2.pdf", extra_data=stamp2)
    doc3 = Document(original_filename="doc3.pdf", extra_data=None)
    
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    db_manager.insert_document(doc3)
    
    # Filter by Cost Center 100
    filters = {"stamps.cost_center": "100"}
    results = db_manager.search_documents(dynamic_filters=filters)
    assert len(results) == 1
    assert results[0].uuid == doc1.uuid
    
    # Filter by Stamp Type 'accounting'
    filters = {"stamps.type": "accounting"}
    results = db_manager.search_documents(dynamic_filters=filters)
    assert len(results) == 1
    assert results[0].uuid == doc2.uuid

def test_last_processed_at_storage(db_manager):
    """Verify last_processed_at is stored and retrieved correctly."""
    now_iso = datetime.now().isoformat()
    doc = Document(original_filename="processed.pdf", last_processed_at=now_iso)
    
    db_manager.insert_document(doc)
    loaded = db_manager.get_document_by_uuid(doc.uuid)
    
    assert loaded is not None
    assert loaded.last_processed_at == now_iso
