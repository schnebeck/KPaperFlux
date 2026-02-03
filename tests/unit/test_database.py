import pytest
import sqlite3
import uuid
import datetime
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument, SourceReference
from core.models.semantic import SemanticExtraction

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
    assert "virtual_documents" in items
    assert "virtual_documents_fts" in items
    assert "semantic_entities" not in items
    assert "documents" not in items 

def test_insert_virtual_document(logical_repo):
    v_doc = VirtualDocument(
        uuid=str(uuid.uuid4()),
        status="NEW",
        created_at=datetime.datetime.now().isoformat(),
        semantic_data=SemanticExtraction(
            meta_header={"sender": {"name": "TestSender"}}
        )
    )
    logical_repo.save(v_doc)
    
    retrieved = logical_repo.get_by_uuid(v_doc.uuid)
    assert retrieved is not None
    assert retrieved.semantic_data.meta_header.sender.name == "TestSender"

    
def test_get_document_by_uuid_stage0(memory_db, logical_repo):
    v_uuid = str(uuid.uuid4())
    v_doc = VirtualDocument(
        uuid=v_uuid,
        status="NEW",
        created_at=datetime.datetime.now().isoformat(),
        export_filename="TestExport"
    )
    logical_repo.save(v_doc)
    
    doc = memory_db.get_document_by_uuid(v_uuid)
    
    assert doc is not None
    assert doc.uuid == v_uuid
    assert doc.original_filename == "TestExport"

def test_delete_document_soft(memory_db, logical_repo):
    v_uuid = str(uuid.uuid4())
    v_doc = VirtualDocument(uuid=v_uuid, created_at="2023-01-01")
    logical_repo.save(v_doc)
    
    # Soft Delete manually via Repo Fetch-Save
    v_doc.deleted = True
    logical_repo.save(v_doc)
    
    # Verify
    retrieved = logical_repo.get_by_uuid(v_uuid)
    assert retrieved.deleted is True
    
    # Verify table state directly
    # but we can check the table.
    cursor = memory_db.connection.cursor()
    cursor.execute("SELECT deleted FROM virtual_documents WHERE uuid = ?", (v_uuid,))
    assert cursor.fetchone()[0] == 1
