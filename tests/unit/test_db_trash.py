
import pytest
import sqlite3
import json
from core.database import DatabaseManager


import pytest
import sqlite3
import json
from core.database import DatabaseManager
from core.document import Document

def test_trash_bin_logic():
    # Use real DB in memory for accurate schema testing
    db = DatabaseManager(":memory:")
    db.init_db()
    
    # Helper to insert using proper API
    def add(uuid_str, filename, deleted):
        doc = Document(
            original_filename=filename,
            uuid=uuid_str, # Override generated UUID
            deleted=deleted
        )
        db.insert_document(doc)

    add("1", "doc1.pdf", deleted=False)
    add("2", "doc2.pdf", deleted=False)
    add("3", "trash.pdf", deleted=True)
    
    # 1. Verify get_all_documents filters deleted
    docs = db.get_all_documents()
    uuids = [d.uuid for d in docs]
    assert "1" in uuids
    assert "2" in uuids
    assert "3" not in uuids
    assert len(docs) == 2
    
    # 2. Verify Soft Delete
    assert db.delete_document("1") == True
    docs = db.get_all_documents()
    assert len(docs) == 1
    assert docs[0].uuid == "2"
    
    # 3. Verify Get Deleted
    trash = db.get_deleted_documents()
    # trash returns Entity Views (uuid = Entity UUID)
    trash_files = [d.original_filename for d in trash]
    assert "doc1.pdf" in trash_files # Just deleted
    assert "trash.pdf" in trash_files # Already deleted
    assert len(trash) == 2
    
    # 4. Verify Restore
    # We use the UUID from the trash list (Entity ID) to verify restore_document handles it.
    trash_doc1 = next(d for d in trash if d.original_filename == "doc1.pdf")
    
    assert db.restore_document(trash_doc1.uuid) == True
    docs = db.get_all_documents()
    assert "1" in [d.uuid for d in docs] # Physical ID is restored
    
    trash = db.get_deleted_documents()
    trash_files_now = [d.original_filename for d in trash]
    assert "doc1.pdf" not in trash_files_now
    
    # 5. Verify Purge (Hard Delete)
    # Use Entity ID from trash list too
    trash_doc3 = next(d for d in trash if d.original_filename == "trash.pdf")
    
    assert db.purge_document(trash_doc3.uuid) == True
    trash = db.get_deleted_documents()
    assert "trash.pdf" not in [d.original_filename for d in trash]
    
    # Verify DB consistency (3 is REALLY gone)
    cursor = db.connection.cursor()
    cursor.execute("SELECT count(*) FROM documents WHERE uuid='3'")
    assert cursor.fetchone()[0] == 0
    cursor.execute("SELECT count(*) FROM semantic_entities WHERE source_doc_uuid='3'")
    assert cursor.fetchone()[0] == 0
