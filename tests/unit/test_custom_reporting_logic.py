
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from core.reporting import ReportGenerator
from core.models.reporting import ReportDefinition, Aggregation
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, MetaHeader, FinanceBody, MonetarySummation

@pytest.fixture
def sample_data():
    """Create 5 documents with varied amounts and dates for testing."""
    docs = []
    # 2026-01: 10.00, 20.00
    # 2026-02: 5.00, 100.00, 200.00
    amounts = [
        ("2026-01-05", Decimal("10.00"), "Sender A"),
        ("2026-01-20", Decimal("20.00"), "Sender A"),
        ("2026-02-01", Decimal("5.00"), "Sender B"),
        ("2026-02-15", Decimal("100.00"), "Sender C"),
        ("2026-02-28", Decimal("200.00"), "Sender C"),
    ]
    
    for i, (date, amt, sender) in enumerate(amounts):
        d = MagicMock(spec=VirtualDocument)
        d.uuid = f"uuid-{i}"
        d.doc_date = date
        d.total_amount = amt
        d.total_net = amt * Decimal("0.8")
        d.sender_name = sender
        d.type_tags = ["INVOICE"]
        d.semantic_data = None # Simplify access using attributes
        docs.append(d)
    return docs

def test_aggregation_min_max_median(sample_data):
    """Test the newly added MIN, MAX, and MEDIAN operations."""
    definition = ReportDefinition(
        id="test-report",
        name="Stats Test",
        group_by=None, # Overall
        aggregations=[
            Aggregation(field="amount", op="min"),
            Aggregation(field="amount", op="max"),
            Aggregation(field="amount", op="median"),
            Aggregation(field="amount", op="sum")
        ]
    )
    
    db_manager = MagicMock()
    # Mocking total documents search
    db_manager.search_documents_advanced.return_value = sample_data
    
    results = ReportGenerator.run_custom_report(db_manager, definition)
    
    # overall group
    assert results["labels"] == ["Overall"]
    series = {s["name"]: s["data"][0] for s in results["series"]}
    
    assert series["MIN(amount)"] == 5.0
    assert series["MAX(amount)"] == 200.0
    assert series["MEDIAN(amount)"] == 20.0 # [5, 10, 20, 100, 200] -> 20 is median
    assert series["SUM(amount)"] == 335.0

def test_percent_of_total(sample_data):
    """Test PERCENT aggregation."""
    definition = ReportDefinition(
        id="test-percent",
        name="Percent Test",
        group_by="doc_date:month",
        aggregations=[
            Aggregation(field="amount", op="sum"),
            Aggregation(field="amount", op="percent")
        ]
    )
    
    db_manager = MagicMock()
    db_manager.search_documents_advanced.return_value = sample_data
    
    results = ReportGenerator.run_custom_report(db_manager, definition)
    
    # Total sum is 335.0
    # Jan: 10 + 20 = 30 -> 30/335 * 100 approx 8.95%
    # Feb: 5 + 100 + 200 = 305 -> 305/335 * 100 approx 91.04%
    
    series = {s["name"]: s["data"] for s in results["series"]}
    # Results are usually sorted by date descending in current implementation? 
    # Let's check the labels order
    idx_jan = results["labels"].index("2026-01")
    idx_feb = results["labels"].index("2026-02")
    
    perc_jan = series["PERCENT(amount)"][idx_jan]
    perc_feb = series["PERCENT(amount)"][idx_feb]
    
    assert pytest.approx(perc_jan, 0.01) == 8.955
    assert pytest.approx(perc_feb, 0.01) == 91.044
    assert pytest.approx(perc_jan + perc_feb, 0.01) == 100.0

def test_amount_bin_grouping(sample_data):
    """Test histogram-like grouping by amount:step."""
    definition = ReportDefinition(
        id="test-bins",
        name="Bin Test",
        group_by="amount:50", # 0-50, 50-100, 100-150, 150-200, 200-250
        aggregations=[Aggregation(field="amount", op="count")]
    )
    
    db_manager = MagicMock()
    db_manager.search_documents_advanced.return_value = sample_data
    
    results = ReportGenerator.run_custom_report(db_manager, definition)
    
    # 10.00 -> 0-50
    # 20.00 -> 0-50
    # 5.00 -> 0-50
    # 100.00 -> 100-150
    # 200.00 -> 200-250
    
    labels = results["labels"]
    counts = results["series"][0]["data"]
    
    data_map = dict(zip(labels, counts))
    assert data_map["0 - 50"] == 3
    assert data_map["100 - 150"] == 1
    assert data_map["200 - 250"] == 1
