import pytest
import os
from core.database import DatabaseManager
from core.document import Document

@pytest.fixture
def db_manager(tmp_path):
    db_path = tmp_path / "test_update.db"
    db = DatabaseManager(str(db_path))
    db.init_db()
    yield db
    db.close()

def test_update_missing_columns(db_manager):
    """
    Test that updating 'sender' and 'doc_date' works.
    This test will FAIL if these columns are not in the allowed_columns list.
    """
    # Create doc
    doc = Document(uuid="1", original_filename="a.pdf")
    db_manager.insert_document(doc)
    
    # Update Sender
    updates = {"sender": "New Sender"}
    success = db_manager.update_document_metadata("1", updates)
    assert success, "Failed to update sender - likely invalid column error"
    
    # Verify
    updated_doc = db_manager.get_document_by_uuid("1")
    assert updated_doc.sender == "New Sender"
    
    # Update Date
    updates_date = {"doc_date": "2025-01-01"}
    success = db_manager.update_document_metadata("1", updates_date)
    assert success, "Failed to update doc_date - likely invalid column error"
    
    updated_doc = db_manager.get_document_by_uuid("1")
    assert updated_doc.doc_date.isoformat() == "2025-01-01"
