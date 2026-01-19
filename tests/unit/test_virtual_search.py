import pytest
from core.database import DatabaseManager

DB_PATH = "kpaperflux.db"

def test_virtual_column_search():
    print("Testing Virtual Column Search Logic...")
    db = DatabaseManager(DB_PATH)
    
    # 1. Simulate a search query for v_sender
    query = {
        "operator": "AND",
        "conditions": [
            {"field": "v_sender", "op": "contains", "value": "Test", "negate": False}
        ]
    }
    
    # 2. Build SQL with the private method (for testing logic) or run search
    # Running search is better integration test
    try:
        results = db.search_documents_advanced(query)
        print(f"Search successful (no SQL errors). Found {len(results)} docs.")
        
        # We expect at least one doc if we ran the previous test
        if len(results) > 0:
            print(f"Sample Doc Sender: {results[0].sender_name} (from JSON!)")
            # Note: Document object doesn't have v_sender attribute, it's mapped to standard columns 
            # OR we need to update Document model to hold it?
            # Actually, standard columns "sender" is legacy. "sender_name" is potentially empty in doc object unless populated from JSON.
            
    except Exception as e:
        pytest.fail(f"Search Failure: {e}")
        
    db.close()

if __name__ == "__main__":
    test_virtual_column_search()
