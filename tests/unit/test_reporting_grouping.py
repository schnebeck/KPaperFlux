
import pytest
from core.reporting import ReportGenerator
from core.models.reporting import ReportDefinition, Aggregation
from decimal import Decimal

def test_generalized_numeric_grouping():
    """
    Verifies that grouping works for non-amount numeric fields like ai_confidence.
    """
    # Mock documents with ai_confidence
    from unittest.mock import MagicMock
    
    docs = []
    data = [
        {"uuid": "1", "ai_confidence": 0.95, "amount": 100},
        {"uuid": "2", "ai_confidence": 0.85, "amount": 200},
        {"uuid": "3", "ai_confidence": 0.55, "amount": 300},
        {"uuid": "4", "ai_confidence": 0.15, "amount": 400},
        {"uuid": "5", "ai_confidence": 0.12, "amount": 500},
    ]
    
    for d in data:
        m = MagicMock()
        m.uuid = d["uuid"]
        m.ai_confidence = d["ai_confidence"]
        m.total_amount = d["amount"]
        m.semantic_data = None
        docs.append(m)
    
    gen = ReportGenerator()
    
    # Define a report grouping by ai_confidence in steps of 0.2
    definition = ReportDefinition(
        id="test_conf",
        name="Confidence Audit",
        group_by="ai_confidence:0.2",
        aggregations=[Aggregation(field="amount", op="sum")],
        components=[]
    )
    
    class MockDB:
        def search_documents_advanced(self, query):
            return docs
            
    results = gen.run_custom_report(MockDB(), definition)
    
    # Expected results:
    # 0.95 -> 0.8 - 1.0
    # 0.85 -> 0.8 - 1.0
    # 0.55 -> 0.4 - 0.6
    # 0.15 -> 0.0 - 0.2
    # 0.12 -> 0.0 - 0.2
    
    labels = results["labels"]
    # Check if '0.8 - 1.0' has sum of 300 (100 + 200)
    # chart_series is now results["series"] based on my view_file check
    data_series = results["series"][0]["data"]
    
    label_to_val = dict(zip(labels, data_series))
    
    # Results with :g formatting:
    # 0.95 // 0.2 = 4 -> 4*0.2 = 0.8, 5*0.2 = 1.0 -> '0.8 - 1'
    # 0.85 // 0.2 = 4 -> 0.8 - 1
    # 0.55 // 0.2 = 2 -> 0.4 - 0.6
    # 0.15 // 0.2 = 0 -> 0 - 0.2
    # 0.12 // 0.2 = 0 -> 0 - 0.2
    
    assert "0.8 - 1" in label_to_val
    assert label_to_val["0.8 - 1"] == 300
    assert label_to_val["0.4 - 0.6"] == 300
    assert label_to_val["0 - 0.2"] == 900
