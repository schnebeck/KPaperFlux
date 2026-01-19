import pytest
from core.database import DatabaseManager
from core.document import Document
import uuid
import json

DB_PATH = "kpaperflux_deep_search_test.db"

def test_deep_search():
    print("Testing Deep Search Logic...")
    
    # 1. Setup DB
    import os
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    db = DatabaseManager(DB_PATH)
    db.init_db()
    
    # 2. Insert Document with deeply nested semantic data
    doc = Document(
        original_filename="deep_invoice.pdf",
        text_content="Some content",
        semantic_data={
            "summary": {
                "sender_name": "Deep Corp",
                "notes": "Payment via Wire"
            },
            "tables": [
                {
                    "id": "table1",
                    "rows": [
                        ["Item A", "100.00", "USD"],
                        ["Item B", "200.00", "USD"]
                    ]
                }
            ]
        }
    )
    db.insert_document(doc)
    
    # 3. Verify Key Discovery
    keys = db.get_available_extra_keys()
    print(f"Discovered Keys: {keys}")
    
    # We expect 'semantic:summary.sender_name', 'semantic:tables.rows' etc.
    assert "semantic:summary.sender_name" in keys
    assert "semantic:tables.rows" in keys or "semantic:tables" in keys
    
    # 4. Perform Search
    # Query 1: Find "Item A" in tables.rows
    query_item = {
        "operator": "AND",
        "conditions": [
            {"field": "semantic:tables.rows", "op": "contains", "value": "Item A", "negate": False}
        ]
    }
    results = db.search_documents_advanced(query_item)
    print(f"Query 'Item A' found: {len(results)} docs.")
    assert len(results) == 1
    assert results[0].uuid == doc.uuid
    
    # Query 2: Find "Deep Corp" in summary.sender_name
    query_sender = {
        "operator": "AND",
        "conditions": [
            {"field": "semantic:summary.sender_name", "op": "equals", "value": "Deep Corp", "negate": False}
        ]
    }
    results = db.search_documents_advanced(query_sender)
    print(f"Query 'Deep Corp' found: {len(results)} docs.")
    assert len(results) == 1

    # Query 3: Negative Test
    query_neg = {
        "operator": "AND",
        "conditions": [
            {"field": "semantic:tables.rows", "op": "contains", "value": "Item Z", "negate": False}
        ]
    }
    results = db.search_documents_advanced(query_neg)
    print(f"Query 'Item Z' found: {len(results)} docs.")
    assert len(results) == 0

    db.close()
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

if __name__ == "__main__":
    test_deep_search()
