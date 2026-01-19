
import pytest
import sqlite3
import json
from core.database import DatabaseManager

class MockDatabaseManager(DatabaseManager):
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.isolation_level = None
        self._init_db()

    def _init_db(self):
        # Full Purified Schema match
        self.connection.execute("""
            CREATE TABLE documents (
                uuid TEXT PRIMARY KEY,
                doc_type TEXT,
                original_filename TEXT,
                export_filename TEXT,
                page_count INTEGER,
                created_at TEXT,
                last_processed_at TEXT,
                locked INTEGER DEFAULT 0,
                deleted INTEGER DEFAULT 0,
                tags TEXT,
                text_content TEXT,
                phash TEXT,
                semantic_data TEXT,
                extra_data TEXT,
                
                v_sender TEXT GENERATED ALWAYS AS (json_extract(semantic_data, '$.summary.sender.name')) VIRTUAL,
                v_doc_date TEXT GENERATED ALWAYS AS (json_extract(semantic_data, '$.summary.main_date')) VIRTUAL,
                v_amount REAL GENERATED ALWAYS AS (json_extract(semantic_data, '$.summary.total_amount')) VIRTUAL
            )
        """)
        
    def add_doc(self, uuid, filename, deleted=False):
        self.connection.execute(
            "INSERT INTO documents (uuid, doc_type, original_filename, deleted, semantic_data) VALUES (?, ?, ?, ?, '{}')",
            (uuid, "[]", filename, 1 if deleted else 0)
        )

def test_trash_bin_logic():
    db = MockDatabaseManager()
    db.add_doc("1", "doc1.pdf", deleted=False)
    db.add_doc("2", "doc2.pdf", deleted=False)
    db.add_doc("3", "trash.pdf", deleted=True)
    
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
    trash_uuids = [d.uuid for d in trash]
    assert "1" in trash_uuids # Just deleted
    assert "3" in trash_uuids # Already deleted
    assert len(trash) == 2
    
    # 4. Verify Restore
    assert db.restore_document("1") == True
    docs = db.get_all_documents()
    assert "1" in [d.uuid for d in docs]
    
    trash = db.get_deleted_documents()
    assert "1" not in [d.uuid for d in trash]
    
    # 5. Verify Purge (Hard Delete)
    assert db.purge_document("3") == True
    trash = db.get_deleted_documents()
    assert "3" not in [d.uuid for d in trash]
    
    # Verify DB consistency (3 is REALLY gone)
    cursor = db.connection.cursor()
    cursor.execute("SELECT count(*) FROM documents WHERE uuid='3'")
    assert cursor.fetchone()[0] == 0
