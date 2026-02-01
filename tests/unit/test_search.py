import pytest
import os
import uuid
import datetime
import sqlite3
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument

@pytest.fixture
def db_manager():
    db = DatabaseManager(":memory:")
    db.init_db()
    return db

@pytest.fixture
def repo(db_manager):
    return LogicalRepository(db_manager)

def test_search_text(db_manager, repo):
    """Test searching by text content."""
    
    cursor = db_manager.connection.cursor()
    
    doc2_uuid = str(uuid.uuid4())
    v_doc2 = VirtualDocument(
        uuid=doc2_uuid,
        cached_full_text="Grocery list: apples, bananas.",
        created_at=datetime.datetime.now().isoformat()
    )
    
    print("Pre-save check...")
    repo.save(v_doc2)
    print("Post-save check...")
    
    f_rows = cursor.execute("SELECT rowid, * FROM virtual_documents_fts").fetchall()
    print(f"DEBUG: FTS Row count: {len(f_rows)}")
    for r in f_rows:
        print(f"DEBUG: FTS Row: {list(r)}")

    results = db_manager.search_documents(search_text="apples")
    assert len(results) == 1
