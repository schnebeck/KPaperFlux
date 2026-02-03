import pytest
import uuid
from decimal import Decimal
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, MetaHeader, FinanceBody, WorkflowInfo, WorkflowLog

@pytest.fixture
def db_manager():
    db = DatabaseManager(":memory:")
    db.init_db()
    return db

@pytest.fixture
def repo(db_manager):
    return LogicalRepository(db_manager)

def test_sum_documents_advanced(db_manager, repo):
    """Requirement: Database can calculate numeric sums based on advanced filters."""
    # Create 3 documents with different amounts
    docs = [
        ("u1", 100.0, "INVOICE"),
        ("u2", 50.0, "RECEIPT"),
        ("u3", 200.0, "INVOICE")
    ]
    
    for uid, amt, dtype in docs:
        v = VirtualDocument(
            uuid=uid,
            type_tags=[dtype],
            semantic_data=SemanticExtraction(
                bodies={"finance_body": FinanceBody(total_gross=Decimal(str(amt)))}
            )
        )
        repo.save(v)
        
    # Query: All documents
    total_all = db_manager.sum_documents_advanced({}, field="amount")
    assert total_all == 350.0
    
    # Query: Only INVOICE
    query_inv = {"field": "type_tags", "op": "contains", "value": ["INVOICE"]}
    total_inv = db_manager.sum_documents_advanced(query_inv, field="amount")
    assert total_inv == 300.0

def test_workflow_persistence(db_manager, repo):
    """Requirement: Workflow metadata is persisted and restored correctly."""
    u1 = "wf-doc-1"
    v1 = VirtualDocument(
        uuid=u1,
        semantic_data=SemanticExtraction(
            workflow=WorkflowInfo(
                is_verified=True,
                pkv_eligible=True,
                current_step="VERIFIED",
                history=[WorkflowLog(action="INITIAL_SCAN"), WorkflowLog(action="MANUAL_VERIFY", user="TEST-USER")]
            )
        )
    )
    repo.save(v1)
    
    # Reload
    v2 = repo.get_by_uuid(u1)
    assert v2.semantic_data.workflow.is_verified is True
    assert v2.semantic_data.workflow.pkv_eligible is True
    assert v2.semantic_data.workflow.current_step == "VERIFIED"
    assert len(v2.semantic_data.workflow.history) == 2
    assert v2.semantic_data.workflow.history[1].user == "TEST-USER"

def test_workflow_actions(db_manager, repo):
    """Requirement: Manual verification updates status, timestamp, and locks document."""
    from datetime import datetime
    u1 = "wf-action-1"
    v1 = VirtualDocument(uuid=u1, status="NEW")
    repo.save(v1)
    
    # 2. Simulate User Clicking "Verify"
    doc = repo.get_by_uuid(u1)
    if not doc.semantic_data:
        from core.models.semantic import SemanticExtraction
        doc.semantic_data = SemanticExtraction()
    
    doc.semantic_data.workflow.is_verified = True
    doc.semantic_data.workflow.verified_at = datetime.now().isoformat()
    doc.semantic_data.workflow.history.append(WorkflowLog(action="VERIFY", user="TestEngine"))
    doc.status = "PROCESSED"
    doc.is_immutable = True
    
    repo.save(doc)
    
    # 3. Verify Reloaded State
    after = repo.get_by_uuid(u1)
    assert after.status == "PROCESSED"
    assert after.is_immutable is True
    assert after.semantic_data.workflow.is_verified is True
    assert after.semantic_data.workflow.history[-1].action == "VERIFY"


def test_sum_advanced_empty_result(db_manager):
    """Requirement: Sum returns 0.0 if no documents match."""
    query = {"field": "status", "op": "eq", "value": "NON_EXISTENT"}
    total = db_manager.sum_documents_advanced(query, field="amount")
    assert total == 0.0

def test_model_serialization(db_manager, repo):
    """Requirement: SemanticExtraction can be dumped to dict for UI/JSON usage."""
    from decimal import Decimal
    sd = SemanticExtraction(
        bodies={"finance_body": FinanceBody(total_gross=Decimal("42.50"))}
    )
    # 1. Test model_dump
    out_dict = sd.model_dump()
    assert isinstance(out_dict["bodies"]["finance_body"], dict)
    assert out_dict["bodies"]["finance_body"]["total_gross"] == Decimal("42.50")
    
    # 2. Test JSON compatibility (simulating GUI debug-view)
    import json
    json_str = json.dumps(out_dict, default=str)
    assert "42.5" in json_str
