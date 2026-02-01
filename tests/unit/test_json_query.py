import pytest
from core.database import DatabaseManager

def test_json_query_generation():
    """
    Verify that JSON fields (prefixed with 'json:') are correctly translated 
    into json_extract SQL calls.
    """
    db = DatabaseManager(":memory:")
    
    query = {
        "field": "json:stamps.cost_center", 
        "op": "equals", 
        "value": "10"
    }
    
    sql, params = db._build_where_clause(query)
    
    print(f"Generated SQL: {sql}")
    print(f"Params: {params}")
    
    # Expected: json_extract(semantic_data, '$.stamps.cost_center') = ? COLLATE NOCASE
    assert "json_extract" in sql
    assert "$.stamps.cost_center" in sql
    assert "10" in params

def test_json_contains_query():
    """Verify JSON 'contains' (LIKE) query."""
    db = DatabaseManager(":memory:")
    query = {
        "field": "json:status", 
        "op": "contains", 
        "value": "ready"
    }
    
    sql, params = db._build_where_clause(query)
    
    print(f"Generated SQL: {sql}")
    print(f"Params: {params}")
    
    # Expected: json_extract(semantic_data, '$.status') LIKE ?
    assert "LIKE" in sql
    assert "json_extract" in sql
    assert "%ready%" in params
