import pytest
import sqlite3
from core.database import DatabaseManager
from core.document import Document
from decimal import Decimal
from datetime import date

@pytest.fixture
def memory_db():
    """Create a temporary in-memory database for testing."""
    return DatabaseManager(":memory:")

def test_init_db(memory_db):
    """Test that tables are created upon initialization."""
    memory_db.init_db()
    
    conn = sqlite3.connect(":memory:") # Mock connection logic needs to be inside class usually, 
                                       # but here we test the effects on the passed db path.
                                       # Wait, DatabaseManager handles the connection. 
                                       # We should check tables via the manager or a fresh connection.
    
    # Let's inspect via the manager's connection if exposed, or verify via SQL
    # For now, let's assume valid SQL execution doesn't raise errors.
    # Better: Inspect sqlite_master
    
    # We need access to the connection to verify
    cursor = memory_db.connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    assert "documents" in tables
    assert "overlays" in tables

def test_insert_document(memory_db):
    """Test inserting a document into the database + Entity creation."""
    memory_db.init_db()
    
    doc = Document(
        original_filename="test.pdf",
        sender="TestSender",
        amount=Decimal("50.00"),
        doc_date=date(2023, 1, 1),
        doc_type="Rechnung"
    )
    
    doc_id = memory_db.insert_document(doc)
    assert doc_id is not None
    assert isinstance(doc_id, int)
    
    # Verify retrieval
    # Note: 'documents' table only has filename. 'sender' is in semantic_entities.
    cursor = memory_db.connection.cursor()
    cursor.execute("SELECT original_filename FROM documents WHERE id=?", (doc_id,))
    row = cursor.fetchone()
    assert row[0] == "test.pdf"
    
    # Verify Semantic Entity Creation
    cursor.execute("SELECT sender_name, doc_date FROM semantic_entities WHERE source_doc_uuid=?", (doc.uuid,))
    ent_row = cursor.fetchone()
    assert ent_row is not None
    assert ent_row[0] == "TestSender"
    assert str(ent_row[1]) == "2023-01-01"

def test_get_all_documents(memory_db):
    """Test retrieving all documents."""
    memory_db.init_db()
    
    doc1 = Document(original_filename="doc1.pdf", sender="A")
    doc2 = Document(original_filename="doc2.pdf", sender="B")
    
    memory_db.insert_document(doc1)
    memory_db.insert_document(doc2)
    
    results = memory_db.get_all_documents() # Returns active docs only
    assert len(results) == 2
    
    # Verify Sorting (DESC created_at) or Order
    # And correct hydration
    filenames = {d.original_filename for d in results}
    assert "doc1.pdf" in filenames
    assert "doc2.pdf" in filenames
    
    # Hydration Check (Entity Join)
    # Finding doc1
    d1 = next(d for d in results if d.original_filename == "doc1.pdf")
    assert d1.sender == "A"

def test_get_document_by_uuid(memory_db):
    """Test retrieving a single document by UUID."""
    memory_db.init_db()
    
    doc = Document(original_filename="target.pdf")
    memory_db.insert_document(doc)
    
    # Success case
    retrieved = memory_db.get_document_by_uuid(doc.uuid)
    assert retrieved is not None
    assert retrieved.uuid == doc.uuid
    assert retrieved.original_filename == "target.pdf"
    
    # Not found case
    assert memory_db.get_document_by_uuid("non-existent-uuid") is None

def test_delete_document(memory_db):
    """Test deleting a document by UUID (Soft Delete)."""
    memory_db.init_db()
    doc = Document(original_filename="todelete.pdf")
    memory_db.insert_document(doc)
    
    # Verify it exists
    assert memory_db.get_document_by_uuid(doc.uuid) is not None
    
    # Delete (Soft)
    success = memory_db.delete_document(doc.uuid)
    assert success is True
    
    # Verify it STILL exists but is marked deleted
    retrieved = memory_db.get_document_by_uuid(doc.uuid)
    assert retrieved is not None
    assert retrieved.deleted is True
    
    # Verify it is EXCLUDED from get_all_documents
    all_docs = memory_db.get_all_documents()
    assert len(all_docs) == 0
    
    # Delete non-existent
    assert memory_db.delete_document("fake-uuid") is False
