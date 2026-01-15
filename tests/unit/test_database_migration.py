
import sqlite3
import pytest
import os
from core.database import DatabaseManager

TEST_DB = "test_migration.db"

@pytest.fixture
def db_path():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    yield TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_schema_migration_v2(db_path):
    """
    Simulate an old database schema and verify that DatabaseManager updates it.
    """
    # 1. Create Old Schema manually
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE NOT NULL,
            original_filename TEXT,
            doc_date DATE,
            sender TEXT,
            amount DECIMAL(10, 2),
            doc_type TEXT,
            phash TEXT,
            text_content TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

    # 2. Add some dummy data
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO documents (uuid, sender, original_filename) VALUES (?, ?, ?)", ("123-abc", "Old Sender", "test.pdf"))
    conn.commit()
    conn.close()

    # 3. Initialize DatabaseManager (should trigger migration)
    mgr = DatabaseManager(db_path=db_path)
    mgr.init_db()

    # 4. Verify new columns exist
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(documents)")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()

    assert "sender_address" in columns
    assert "iban" in columns
    assert "phone" in columns
    assert "tags" in columns
    
    # 5. Verify old data remains
    doc = mgr.get_document_by_uuid("123-abc")
    assert doc is not None
    assert doc.sender == "Old Sender"
    
    # 6. Verify we can write to new cols
    mgr.update_document_metadata("123-abc", {"sender_address": "Musterstraße 1"})
    
    doc_updated = mgr.get_document_by_uuid("123-abc")
    assert doc_updated.sender_address == "Musterstraße 1"
