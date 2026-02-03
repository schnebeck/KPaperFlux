import pytest
import uuid
from decimal import Decimal
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, MetaHeader, FinanceBody, AddressInfo

@pytest.fixture
def db_manager():
    db = DatabaseManager(":memory:")
    db.init_db()
    return db

@pytest.fixture
def repo(db_manager):
    return LogicalRepository(db_manager)

def test_filter_by_sender_name(db_manager, repo):
    """Test filtering by sender name in the new nested semantic structure."""
    u1 = str(uuid.uuid4())
    v1 = VirtualDocument(
        uuid=u1,
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name="Amazon"))
        )
    )
    repo.save(v1)
    
    u2 = str(uuid.uuid4())
    v2 = VirtualDocument(
        uuid=u2,
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(sender=AddressInfo(name="Google"))
        )
    )
    repo.save(v2)
    
    query = {
        "field": "sender",
        "op": "contains",
        "value": ["Amazon"]
    }
    
    results = db_manager.search_documents_advanced(query)
    
    assert len(results) == 1
    assert results[0].uuid == u1

def test_filter_by_amount_range(db_manager, repo):
    """Test filtering by amount in the new nested semantic structure."""
    u1 = str(uuid.uuid4())
    v1 = VirtualDocument(
        uuid=u1,
        semantic_data=SemanticExtraction(
            bodies={"finance_body": FinanceBody(total_gross=Decimal("150.00"))}
        )
    )
    repo.save(v1)
    
    u2 = str(uuid.uuid4())
    v2 = VirtualDocument(
        uuid=u2,
        semantic_data=SemanticExtraction(
            bodies={"finance_body": FinanceBody(total_gross=Decimal("50.00"))}
        )
    )
    repo.save(v2)
    
    # Amount > 100
    query = {
        "field": "amount",
        "op": "gt",
        "value": 100
    }
    
    results = db_manager.search_documents_advanced(query)
    
    assert len(results) == 1
    assert results[0].uuid == u1

def test_filter_by_doc_date(db_manager, repo):
    """Test filtering by doc_date in the new nested semantic structure."""
    u1 = str(uuid.uuid4())
    v1 = VirtualDocument(
        uuid=u1,
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date="2023-01-01")
        )
    )
    repo.save(v1)
    
    u2 = str(uuid.uuid4())
    v2 = VirtualDocument(
        uuid=u2,
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date="2023-02-01")
        )
    )
    repo.save(v2)
    
    query = {
        "field": "doc_date",
        "op": "starts_with",
        "value": "2023-01"
    }
    
    results = db_manager.search_documents_advanced(query)
    
    assert len(results) == 1
    assert results[0].uuid == u1
