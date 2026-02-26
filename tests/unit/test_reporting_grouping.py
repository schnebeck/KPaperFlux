
import pytest
from core.reporting import ReportGenerator
from core.models.reporting import ReportDefinition, Aggregation
from decimal import Decimal

def test_generalized_numeric_grouping():
    """
    Verifies that grouping works for non-amount numeric fields like ai_confidence.
    """
    # Mock documents with ai_confidence
    docs = [
        {"uuid": "1", "ai_confidence": 0.95, "amount": 100},
        {"uuid": "2", "ai_confidence": 0.85, "amount": 200},
        {"uuid": "3", "ai_confidence": 0.55, "amount": 300},
        {"uuid": "4", "ai_confidence": 0.15, "amount": 400},
        {"uuid": "5", "ai_confidence": 0.12, "amount": 500},
    ]
    
    gen = ReportGenerator()
    
    # Define a report grouping by ai_confidence in steps of 0.2
    # Format: field:step
    definition = ReportDefinition(
        id="test_conf",
        name="Confidence Audit",
        group_by="ai_confidence:0.2",
        aggregations=[Aggregation(field="amount", op="sum")],
        components=[]
    )
    
    # We need to mock the DB search or pass the docs directly if the API allows
    # Looking at core/reporting.py, it likely takes a db_manager.
    # We might need to mock the db_manager.
    
    class MockDB:
        def search_documents_advanced(self, query):
            return docs
            
    results = gen.run_custom_report(MockDB(), definition)
    
    # Expected groups: 
    # 0.0 - 0.2: [4, 5] -> sum=900
    # 0.4 - 0.6: [3] -> sum=300
    # 0.8 - 1.0: [1, 2] -> sum=300
    
    labels = results["chart_labels"]
    data = results["chart_series"][0]["data"]
    
    assert "0.0 - 0.2" in labels
    assert 900 in data
    assert "0.8 - 1.0" in labels
    assert 300 in data
