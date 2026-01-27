import pytest
import uuid
import datetime
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

def test_advanced_filter_type_tags_contains(db_manager, repo):
    # Setup: 3 documents
    # 1. INBOUND
    # 2. OUTBOUND
    # 3. BOTH
    # 4. DELETED INBOUND
    
    u1 = str(uuid.uuid4())
    v1 = VirtualDocument(uuid=u1, type_tags=["INBOUND"], created_at="2024-01-01T10:00:00")
    repo.save(v1)
    
    u2 = str(uuid.uuid4())
    v2 = VirtualDocument(uuid=u2, type_tags=["OUTBOUND"], created_at="2024-01-01T10:01:00")
    repo.save(v2)
    
    u3 = str(uuid.uuid4())
    v3 = VirtualDocument(uuid=u3, type_tags=["INBOUND", "INVOICE"], created_at="2024-01-01T10:02:00")
    repo.save(v3)
    
    u4 = str(uuid.uuid4())
    v4 = VirtualDocument(uuid=u4, type_tags=["INBOUND"], deleted=True, created_at="2024-01-01T10:03:00")
    repo.save(v4)
    
    # 1. Filter for INBOUND (Contains)
    query = {
        "operator": "AND",
        "conditions": [
            {"field": "type_tags", "op": "contains", "value": ["INBOUND"], "negate": False}
        ]
    }
    
    results = db_manager.search_documents_advanced(query)
    
    # Expected: v1 and v3 (v2 is outbound, v4 is deleted)
    assert len(results) == 2
    uuids = [d.uuid for d in results]
    assert u1 in uuids
    assert u3 in uuids
    assert u2 not in uuids
    assert u4 not in uuids

def test_advanced_filter_type_tags_contains_multiple(db_manager, repo):
    # Setup
    u1 = str(uuid.uuid4())
    v1 = VirtualDocument(uuid=u1, type_tags=["INBOUND"], created_at="2024-01-01T10:00:00")
    repo.save(v1)
    
    u2 = str(uuid.uuid4())
    v2 = VirtualDocument(uuid=u2, type_tags=["OUTBOUND"], created_at="2024-01-01T10:01:00")
    repo.save(v2)
    
    u3 = str(uuid.uuid4())
    v3 = VirtualDocument(uuid=u3, type_tags=["INTERNAL"], created_at="2024-01-01T10:02:00")
    repo.save(v3)
    
    # Filter for INBOUND or OUTBOUND
    query = {
        "operator": "AND",
        "conditions": [
            {"field": "type_tags", "op": "contains", "value": ["INBOUND", "OUTBOUND"], "negate": False}
        ]
    }
    
    results = db_manager.search_documents_advanced(query)
    
    # Expected: v1 and v2
    assert len(results) == 2
    uuids = [d.uuid for d in results]
    assert u1 in uuids
    assert u2 in uuids
    assert u3 not in uuids

def test_advanced_filter_negated_type_tags(db_manager, repo):
    # Setup
    u1 = str(uuid.uuid4())
    v1 = VirtualDocument(uuid=u1, type_tags=["INBOUND"], created_at="2024-01-01T10:00:00")
    repo.save(v1)
    
    u2 = str(uuid.uuid4())
    v2 = VirtualDocument(uuid=u2, type_tags=["OUTBOUND"], created_at="2024-01-01T10:01:00")
    repo.save(v2)
    
    # Filter for NOT Contains INBOUND
    query = {
        "operator": "AND",
        "conditions": [
            {"field": "type_tags", "op": "contains", "value": ["INBOUND"], "negate": True}
        ]
    }
    
    results = db_manager.search_documents_advanced(query)
    
    # Expected: v2
    assert len(results) == 1
    assert results[0].uuid == u2

def test_advanced_filter_type_tags_partial_mismatch(db_manager, repo):
    # Setup
    u1 = str(uuid.uuid4())
    v1 = VirtualDocument(uuid=u1, type_tags=["INBOUND_MARKER"], created_at="2024-01-01T10:00:00")
    repo.save(v1)
    
    u2 = str(uuid.uuid4())
    v2 = VirtualDocument(uuid=u2, type_tags=["MARKER"], created_at="2024-01-01T10:01:00")
    repo.save(v2)
    
    # Filter for INBOUND
    query = {
        "operator": "AND",
        "conditions": [
            {"field": "type_tags", "op": "contains", "value": ["INBOUND"], "negate": False}
        ]
    }
    
    results = db_manager.search_documents_advanced(query)
    
    # Expected: 0 results now because we use exact element matching
    assert len(results) == 0
