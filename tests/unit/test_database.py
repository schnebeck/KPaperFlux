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
    """Test inserting a document into the database."""
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
    cursor = memory_db.connection.cursor()
    cursor.execute("SELECT original_filename, amount, sender FROM documents WHERE id=?", (doc_id,))
    row = cursor.fetchone()
    
    assert row[0] == "test.pdf"
    assert row[1] == 50.0  # SQLite stores decimal as REAL or TEXT, usually REAL/NUMERIC
    assert row[2] == "TestSender"

def test_get_all_documents(memory_db):
    """Test retrieving all documents."""
    memory_db.init_db()
    
    doc1 = Document(original_filename="doc1.pdf", sender="A")
    doc2 = Document(original_filename="doc2.pdf", sender="B")
    
    memory_db.insert_document(doc1)
    memory_db.insert_document(doc2)
    
    results = memory_db.get_all_documents()
    assert len(results) == 2
    # Check that we get Document objects or at least dicts. 
    # For MVP, dicts or Pydantic models are fine. Let's assume Pydantic models ideally, 
    # but re-hydrating might be complex without extra logic. 
    # Let's start with dicts or rows if that's easier, or full Documents if we implemented it.
    # Plan didn't specify return type rigorously, so let's expect a list of dicts for TableWidget easier consumption.
    
    # Actually, DatabaseManager returning Document objects is cleaner architecture.
    assert isinstance(results[0], Document)
    assert results[0].original_filename == "doc1.pdf"
    assert results[1].original_filename == "doc2.pdf"

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
    """Test deleting a document by UUID."""
    memory_db.init_db()
    doc = Document(original_filename="todelete.pdf")
    memory_db.insert_document(doc)
    
    # Verify it exists
    assert memory_db.get_document_by_uuid(doc.uuid) is not None
    
    # Delete
    success = memory_db.delete_document(doc.uuid)
    assert success is True
    
    # Verify it's gone
    assert memory_db.get_document_by_uuid(doc.uuid) is None
    
    # Delete non-existent
    assert memory_db.delete_document("fake-uuid") is False
