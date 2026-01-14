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
