
import pytest
from core.database import DatabaseManager
from core.document import Document
import os

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "phase8.db"
    db_man = DatabaseManager(str(db_path))
    db_man.init_db()
    return db_man

def test_migration_and_fields(db):
    # Verify migration works (columns exist)
    # Using pragma to check columns
    cursor = db.connection.cursor()
    cursor.execute("PRAGMA table_info(documents)")
    cols = [r[1] for r in cursor.fetchall()]
    
    assert "recipient_city" in cols
    assert "sender_zip" in cols
    assert "page_count" in cols
    assert "created_at" in cols
    
def test_insert_and_retrieve_extended(db):
    doc = Document(
        original_filename="test.pdf",
        recipient_name="Hans",
        recipient_city="Berlin",
        sender_company="Amazon",
        page_count=5
    )
    
    doc.created_at = "2024-01-01T10:00:00"
    
    db.insert_document(doc)
    
    retrieved = db.get_document_by_uuid(doc.uuid)
    assert retrieved.recipient_name == "Hans"
    assert retrieved.recipient_city == "Berlin"
    assert retrieved.sender_company == "Amazon"
    assert retrieved.page_count == 5
    assert retrieved.created_at == "2024-01-01T10:00:00"
    
    # Update extended
    db.update_document_metadata(doc.uuid, {"recipient_zip": "10115", "page_count": 6})
    retrieved2 = db.get_document_by_uuid(doc.uuid)
    assert retrieved2.recipient_zip == "10115"
    assert retrieved2.page_count == 6
