
import pytest
from core.similarity import SimilarityManager
from core.models.virtual import VirtualDocument as Document
from core.models.semantic import SemanticExtraction, MetaHeader, FinanceBody
from core.database import DatabaseManager
from unittest.mock import MagicMock
import datetime
from decimal import Decimal

@pytest.fixture
def mock_db():
    return MagicMock(spec=DatabaseManager)

def test_calculate_similarity_exact():
    doc_a = Document(original_filename="a.pdf", text_content="hello world this is a test")
    doc_b = Document(original_filename="b.pdf", text_content="hello world this is a test")
    
    manager = SimilarityManager(None)
    score = manager.calculate_similarity(doc_a, doc_b)
    
    assert score == 1.0

def test_calculate_similarity_jaccard():
    # "is" vs "is" matches. "a" matches. "test" matches.
    # intersection: hello, world, this, is, a, test (6)
    # union: 6 + "foo" (7) -> 6/7 ~ 0.85
    doc_a = Document(original_filename="a.pdf", text_content="hello world this is a test")
    doc_b = Document(original_filename="b.pdf", text_content="hello world this is a test foo")
    
    manager = SimilarityManager(None)
    score = manager.calculate_similarity(doc_a, doc_b)
    
    assert 0.8 < score < 1.0

def test_metadata_boost():
    # Low text similarity but Perfect Metadata
    today = "2024-01-01"
    doc_a = Document(
        original_filename="a.pdf", 
        text_content="invoice amazon delivery", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date=today),
            bodies={"finance_body": FinanceBody(total_gross=Decimal("10.00"))}
        )
    )
    doc_b = Document(
        original_filename="b.pdf", 
        text_content="invoice google play", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date=today),
            bodies={"finance_body": FinanceBody(total_gross=Decimal("10.00"))}
        )
    )
    
    manager = SimilarityManager(None)
    # Text Jaccard: "invoice" (1) / "amazon", "delivery", "google", "play", "invoice" (5) = 0.2
    # Metadata Boost: Date match (+0.2) + Amount match (+0.3) = 0.5.
    # Score >= 0.5 triggers +0.2 boost.
    # Final = 0.2 + 0.2 = 0.4.
    
    score = manager.calculate_similarity(doc_a, doc_b)
    assert score >= 0.4
    
    # High text sim + metadata
    doc_c = Document(
        original_filename="c.pdf", 
        text_content="invoice amazon delivery items", 
        semantic_data=SemanticExtraction(
            meta_header=MetaHeader(doc_date=today),
            bodies={"finance_body": FinanceBody(total_gross=Decimal("10.00"))}
        )
    )
    # Jaccard ~ 0.6
    # Final = 0.6 + 0.2 = 0.8.
    score2 = manager.calculate_similarity(doc_a, doc_c)
    assert score2 >= 0.8

def test_find_duplicates(mock_db):
    docs = [
        Document(uuid="1", original_filename="a.pdf", text_content="apple banana"),
        Document(uuid="2", original_filename="b.pdf", text_content="apple banana checkbox"),
        Document(uuid="3", original_filename="c.pdf", text_content="completely different")
    ]
    mock_db.get_all_entities_view.return_value = docs
    
    manager = SimilarityManager(mock_db)
    duplicates = manager.find_duplicates(threshold=0.5)
    
    # 1 and 2 should match (Jaccard ~0.66)
    # 1 and 3 (0.0)
    # 2 and 3 (0.0)
    
    assert len(duplicates) == 1
    assert duplicates[0][0].uuid == "1"
    assert duplicates[0][1].uuid == "2"
