import pytest
from core.database import DatabaseManager

def test_sender_company_filter_generation():
    """
    Reproduction of user report: Filter 'sender_company' is ignored in SQL generation.
    """
    # Mock parameters
    query = {
        "operator": "AND", 
        "conditions": [
            {"field": "sender_company", "op": "contains", "value": "Beckhoff"}
        ]
    }
    params = []
    
    # We can test _build_advanced_sql directly without a real DB connection if we sub-class or mock
    # But DatabaseManager likely needs init. Let's make a dummy one.
    db = DatabaseManager(":memory:")
    
    sql_part = db._build_advanced_sql(query, params)
    
    print(f"Generated SQL Part: '{sql_part}'")
    
    # Expectation: SQL should NOT be empty and should contain sender_company
    assert sql_part != "", "Generated SQL WHERE clause is empty!"
    assert "sender_company" in sql_part
    assert "LIKE" in sql_part
    assert "%Beckhoff%" in params[0] or "Beckhoff" in params[0]

def test_expanded_columns_generation():
    """Test other new columns."""
    db = DatabaseManager(":memory:")
    
    fields_to_test = [
        "recipient_city", "iban", "text_content", "gross_amount"
    ]
    
    for f in fields_to_test:
        q = {"field": f, "op": "equals", "value": "test"}
        p = []
        sql = db._build_advanced_sql(q, p)
        assert sql != "", f"Failed to generate SQL for field: {f}"
        assert f in sql
