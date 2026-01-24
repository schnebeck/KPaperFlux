import pytest
import sqlite3
import uuid
import datetime
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument, SourceReference

@pytest.fixture
def memory_db():
    db = DatabaseManager(":memory:")
    db.init_db()
    return db

@pytest.fixture
def logical_repo(memory_db):
    return LogicalRepository(memory_db)

def test_init_db(memory_db):
    cursor = memory_db.connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view');")
    items = [row[0] for row in cursor.fetchall()]
    assert "physical_files" in items
    assert "semantic_entities" in items
    assert "documents" in items 

def test_insert_virtual_document(logical_repo):
    v_doc = VirtualDocument(
        entity_uuid=str(uuid.uuid4()),
        sender_name="TestSender",
        doc_date="2023-01-01",
        created_at=datetime.datetime.now().isoformat()
    )
    logical_repo.save(v_doc)
    
    retrieved = logical_repo.get_by_uuid(v_doc.entity_uuid)
    assert retrieved is not None
    assert retrieved.sender_name == "TestSender"
    
def test_get_document_by_uuid_legacy(memory_db, logical_repo):
    # Setup legacy-compatible entity (needs valid types)
    v_doc = VirtualDocument(
        entity_uuid=str(uuid.uuid4()),
        sender_name="LegacySender",
        created_at=datetime.datetime.now().isoformat()
        # Source Mapping defaults to []
    )
    logical_repo.save(v_doc)
    
    doc = memory_db.get_document_by_uuid(v_doc.entity_uuid)
    
    assert doc is not None
    assert doc.uuid == v_doc.entity_uuid
    assert doc.sender == "LegacySender"

def test_delete_document_soft(memory_db, logical_repo):
    v_doc = VirtualDocument(entity_uuid=str(uuid.uuid4()), created_at="2023-01-01")
    logical_repo.save(v_doc)
    
    # Soft Delete manually via Repo Fetch-Save
    v_doc.deleted = True
    logical_repo.save(v_doc)
    
    # Verify
    retrieved = logical_repo.get_by_uuid(v_doc.entity_uuid)
    assert retrieved.deleted is True
    
    # Legacy DB check
    doc = memory_db.get_document_by_uuid(v_doc.entity_uuid)
    assert doc.deleted is True
