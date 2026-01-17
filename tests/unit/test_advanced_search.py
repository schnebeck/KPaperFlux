import pytest
import os
from core.document import Document
from core.database import DatabaseManager

TEST_DB = "test_advanced_search.db"

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

def test_advanced_search_numeric(db_manager):
    """Test numeric comparisons (>, <)."""
    doc1 = Document(original_filename="A.pdf", amount=50.0)
    doc2 = Document(original_filename="B.pdf", amount=100.0)
    doc3 = Document(original_filename="C.pdf", amount=150.0)
    
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    db_manager.insert_document(doc3)
    
    # Amount > 80
    query = {
        "field": "amount",
        "op": "gt",
        "value": 80
    }
    results = db_manager.search_documents_advanced(query)
    assert len(results) == 2
    uuids = [d.uuid for d in results]
    assert doc2.uuid in uuids
    assert doc3.uuid in uuids

def test_advanced_search_logic_and(db_manager):
    """Test AND logic groups."""
    doc1 = Document(original_filename="Invoice_Amazon.pdf", sender="Amazon", amount=100.0)
    doc2 = Document(original_filename="Invoice_Google.pdf", sender="Google", amount=100.0)
    doc3 = Document(original_filename="Offer_Amazon.pdf", sender="Amazon", amount=20.0)
    
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    db_manager.insert_document(doc3)
    
    # Sender='Amazon' AND Amount > 50
    query = {
        "operator": "AND",
        "conditions": [
            {"field": "sender", "op": "equals", "value": "Amazon"},
            {"field": "amount", "op": "gt", "value": 50}
        ]
    }
    results = db_manager.search_documents_advanced(query)
    assert len(results) == 1
    assert results[0].uuid == doc1.uuid

def test_advanced_search_json(db_manager):
    """Test searching into JSON extra_data."""
    doc1 = Document(original_filename="1.pdf", extra_data={"status": "paid"})
    doc2 = Document(original_filename="2.pdf", extra_data={"status": "open"})
    
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    
    # extra_data.status == 'paid'
    query = {
        "field": "json:status",
        "op": "equals",
        "value": "paid"
    }
    results = db_manager.search_documents_advanced(query)
    assert len(results) == 1
    assert results[0].uuid == doc1.uuid

def test_advanced_search_complex_nested(db_manager):
    """Test nested OR/AND logic."""
    # (Sender=Amazon) OR (Amount > 200)
    doc1 = Document(original_filename="Amazon.pdf", sender="Amazon", amount=10.0)
    doc2 = Document(original_filename="Big.pdf", sender="Unknown", amount=500.0)
    doc3 = Document(original_filename="Small.pdf", sender="Unknown", amount=50.0)
    
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    db_manager.insert_document(doc3)
    
    query = {
        "operator": "OR",
        "conditions": [
            {"field": "sender", "op": "equals", "value": "Amazon"},
            {"field": "amount", "op": "gt", "value": 200}
        ]
    }
    results = db_manager.search_documents_advanced(query)
    assert len(results) == 2
    uuids = [d.uuid for d in results]
    assert doc1.uuid in uuids
    assert doc2.uuid in uuids
