import pytest
import os
import json
from core.database import DatabaseManager
from core.document import Document

TEST_DB = "test_dynamic_cols.db"

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

def test_get_available_extra_keys(db_manager):
    """Test extracting unique keys from extra_data JSON."""
    
    # Doc 1: Flat
    doc1 = Document(original_filename="doc1.pdf", extra_data={"cost_center": "100", "approved": True})
    
    # Doc 2: Nested
    doc2 = Document(original_filename="doc2.pdf", extra_data={"stamps": {"type": "entry", "date": "2023"}})
    
    # Doc 3: Mixed overlap
    doc3 = Document(original_filename="doc3.pdf", extra_data={"cost_center": "200", "stamps": {"user": "admin"}})
    
    # Doc 4: List inside (should be handled gracefully, likely ignored or just top level)
    # Our implementation: recurses dicts. If list, currently ignores elements or adds key?
    # Logic was: if dict recurse, else add key. So "tags": ["a", "b"] -> key "tags" added.
    # Doc 4: List inside (should be handled gracefully)
    # New logic: Recurse into list items (dicts)
    doc4 = Document(original_filename="doc4.pdf", extra_data={"flags": ["urgent"], "stamps": [{"cost_center": "ABC", "approved": True}]})
    
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    db_manager.insert_document(doc3)
    db_manager.insert_document(doc4)
    
    keys = db_manager.get_available_extra_keys()
    
    # Expected: 
    # cost_center (1, 3)
    # approved (1)
    # stamps.type (2)
    # stamps.date (2)
    # stamps.user (3)
    # flags (4)
    # stamps (2, 3, 4) - List key itself
    # stamps.cost_center (4) - Deep discovery
    # stamps.approved (4) - Deep discovery
    
    expected = sorted([
        "cost_center", "approved", 
        "stamps", "stamps.type", "stamps.date", "stamps.user", 
        "flags", 
        "stamps.cost_center", "stamps.approved"
    ])
    
    assert keys == expected
