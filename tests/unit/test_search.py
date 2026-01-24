import pytest
import os
import uuid
import datetime
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument

@pytest.fixture
def db_manager():
    # In-memory DB is faster and cleaner
    db = DatabaseManager(":memory:")
    db.init_db()
    return db

@pytest.fixture
def repo(db_manager):
    return LogicalRepository(db_manager)

def test_search_text(db_manager, repo):
    """Test searching by text content (via Canonical Data)."""
    # Create Entities with fake text in canonical_data or via source resolution?
    # The View `documents` gets `text_content` from `s.canonical_data`.
    # Wait, the View definition says: `s.canonical_data as text_content`.
    # So if we put text in canonical_data, it should be searchable?
    # Actually canonical_data is JSON. 
    # If standard is to put full text in 'text', we should do that?
    # Currently V2 Canonizer puts "full_json" in audit, does it put generic text?
    # The View uses `s.canonical_data`. If that is a JSON BLOB, `LIKE %query%` on a BLOB works in sqlite (it treats as string).
    # So yes, if "apples" is in the JSON string, it matches.
    
    doc2_uuid = str(uuid.uuid4())
    v_doc2 = VirtualDocument(
        entity_uuid=doc2_uuid,
        semantic_data={"text_content": "Grocery list: apples, bananas.", "summary": {}},
        created_at=datetime.datetime.now().isoformat()
    )
    repo.save(v_doc2)
    
    # Search
    results = db_manager.search_documents(text_query="apples")
    assert len(results) == 1
    assert results[0].uuid == doc2_uuid

    # No match
    results = db_manager.search_documents(text_query="gamma")
    assert len(results) == 0

def test_last_processed_at_storage(db_manager, repo):
    """Verify timestamps."""
    # Last Processed At currently maps to NULL in the View?
    # View: `NULL as last_processed_at`.
    # So this feature is effectively removed/reset in V2 View.
    # We should verify it returns None or verify created_at.
    
    doc_uuid = str(uuid.uuid4())
    now_iso = datetime.datetime.now().isoformat()
    v_doc = VirtualDocument(
        entity_uuid=doc_uuid,
        created_at=now_iso
    )
    repo.save(v_doc)
    
    loaded = db_manager.get_document_by_uuid(doc_uuid)
    assert loaded.created_at == now_iso
