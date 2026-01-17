import pytest
from core.database import DatabaseManager

def test_json_query_generation():
    """
    Verify that JSON fields (prefixed with 'json:') are correctly translated 
    into json_extract SQL calls.
    """
    db = DatabaseManager(":memory:")
    
    # query = {field: "json:stamps.cost_center", op: "equals", value: "10"}
    query = {
        "field": "json:stamps.cost_center", 
        "op": "equals", 
        "value": "10"
    }
    params = []
    
    sql = db._build_advanced_sql(query, params)
    
    print(f"Generated SQL: {sql}")
    
    # Expected: EXISTS (SELECT 1 FROM json_tree(documents.extra_data) WHERE fullkey LIKE ? AND value = ?)
    # Params: ["%stamps%cost_center%", "10"]
    assert "EXISTS" in sql
    assert "json_tree" in sql
    assert "fullkey LIKE" in sql
    assert "%stamps%cost_center%" in params
    assert "10" in params

def test_json_contains_query():
    """Verify JSON 'contains' (LIKE) query."""
    db = DatabaseManager(":memory:")
    query = {
        "field": "json:status", 
        "op": "contains", 
        "value": "ready"
    }
    params = []
    
    sql = db._build_advanced_sql(query, params)
    
    # LIKE should be used in value check
    assert "LIKE" in sql
    # Params order: [pattern, value] -> ["%status%", "%ready%"]
    assert "%status%" in params
    assert "%ready%" in params
