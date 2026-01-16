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
    doc4 = Document(original_filename="doc4.pdf", extra_data={"flags": ["urgent"]})
    
    db_manager.insert_document(doc1)
    db_manager.insert_document(doc2)
    db_manager.insert_document(doc3)
    db_manager.insert_document(doc4)
    
    keys = db_manager.get_available_extra_keys()
    
    # Expected: 
    # cost_center (from 1 & 3)
    # approved (from 1)
    # stamps.type (from 2)
    # stamps.date (from 2)
    # stamps.user (from 3)
    # flags (from 4)
    
    expected = sorted(["cost_center", "approved", "stamps.type", "stamps.date", "stamps.user", "flags"])
    
    assert keys == expected
