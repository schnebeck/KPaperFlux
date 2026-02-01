import pytest
from core.database import DatabaseManager

DB_PATH = ":memory:" # Use memory for unit test

def test_virtual_column_search():
    """Verify that virtual fields (mapped to JSON) generate correct SQL and execute."""
    db = DatabaseManager(DB_PATH)
    
    # 1. Simulate a search query for 'sender' (mapped to JSON)
    query = {
        "operator": "AND",
        "conditions": [
            {"field": "sender", "op": "contains", "value": "Test", "negate": False}
        ]
    }
    
    # 2. Build SQL and execute
    # Note: search_documents_advanced should not crash
    try:
        results = db.search_documents_advanced(query)
        # We expect 0 results on empty DB, but success (no OperationalError)
        assert isinstance(results, list)
        
    except Exception as e:
        pytest.fail(f"Search Failure: {e}")
        
    db.close()

def test_semantic_prefix_search():
    """Verify the 'semantic:' prefix works for deep JSON mapping."""
    db = DatabaseManager(":memory:")
    query = {
        "field": "semantic:meta_header.doc_id", 
        "op": "equals", 
        "value": "123"
    }
    
    sql, params = db._build_where_clause(query)
    assert "json_extract" in sql
    assert "$.meta_header.doc_id" in sql
    assert "123" in params
