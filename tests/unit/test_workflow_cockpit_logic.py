import pytest
import uuid
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, WorkflowInfo

@pytest.fixture
def db_manager():
    db = DatabaseManager(":memory:")
    db.init_db()
    return db

@pytest.fixture
def repo(db_manager):
    return LogicalRepository(db_manager)

def test_workflow_step_filtering(db_manager, repo):
    """Verify that we can filter documents by their current workflow step."""
    u1 = str(uuid.uuid4())
    v1 = VirtualDocument(
        uuid=u1,
        semantic_data=SemanticExtraction(
            workflow=WorkflowInfo(current_step="URGENT")
        )
    )
    repo.save(v1)
    
    u2 = str(uuid.uuid4())
    v2 = VirtualDocument(
        uuid=u2,
        semantic_data=SemanticExtraction(
            workflow=WorkflowInfo(current_step="NEW")
        )
    )
    repo.save(v2)
    
    # Query using the 'semantic:workflow.current_step' path
    query = {
        "field": "semantic:workflow.current_step",
        "op": "equals",
        "value": "URGENT"
    }
    
    results = db_manager.search_documents_advanced(query)
    assert len(results) == 1
    assert results[0].uuid == u1
    
    # Test count_documents_advanced
    count = db_manager.count_documents_advanced(query)
    assert count == 1

def test_workflow_step_trend_data(db_manager, repo):
    """Verify that we can get trend data for specific workflow steps."""
    # We'll insert a few documents with different dates (simulated via created_at if doc_date missing)
    # Actually, let's use doc_date to be sure
    
    for i in range(5):
        u = str(uuid.uuid4())
        v = VirtualDocument(
            uuid=u,
            semantic_data=SemanticExtraction(
                workflow=WorkflowInfo(current_step="URGENT"),
                meta_header={"doc_date": f"2026-02-{10+i}"}
            )
        )
        repo.save(v)
        
    query = {
        "field": "semantic:workflow.current_step",
        "op": "equals",
        "value": "URGENT"
    }
    
    # aggregation="count" should return 5 points of 1.0 (or something similar depending on binning)
    trend = db_manager.get_trend_data_advanced(query, days=30, aggregation="count")
    
    # Filter out zeros to see if we got our data
    active_points = [p for p in trend if p > 0]
    assert len(active_points) >= 1
    assert sum(active_points) == 5
