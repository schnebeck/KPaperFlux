import sys
import os
import sqlite3
import uuid
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import DatabaseManager

def test_page_count_retrieval():
    print(">>> TEST: Reproduce Page Count Bug in View")
    
    # 1. Setup In-Memory DB
    db = DatabaseManager(":memory:")
    db.init_db()
    
    # 2. Insert Physical File (Known 3 pages)
    file_id = str(uuid.uuid4())
    print(f"Inserting Physical File {file_id} (Page Count=3)...")
    db.connection.execute("""
        INSERT INTO physical_files (file_uuid, page_count, original_filename) 
        VALUES (?, ?, ?)
    """, (file_id, 3, "test.pdf"))
    
    # 3. Insert Semantic Entity (Linked to File)
    entity_id = str(uuid.uuid4())
    # Note: We do NOT populate 'page_ranges' (Legacy). We populate 'source_mapping' (New).
    source_map = [{"file_uuid": file_id, "pages": [1,2,3], "rotation": 0}]
    
    print(f"Inserting Entity {entity_id} linked to {file_id}...")
    db.connection.execute("""
        INSERT INTO semantic_entities (entity_uuid, source_doc_uuid, doc_type, status, source_mapping)
        VALUES (?, ?, ?, ?, ?)
    """, (entity_id, file_id, "UNKNOWN", "NEW", json.dumps(source_map)))
    
    # 4. Fetch via get_document_by_uuid (Which uses 'documents' VIEW)
    print("Fetching document via Manager...")
    doc = db.get_document_by_uuid(entity_id)
    
    if not doc:
        print("FAIL: Document not found!")
        return

    print(f"Retrieved Page Count: {doc.page_count}")
    
    if doc.page_count != 3:
        print(f"FAIL: Expected 3, got {doc.page_count}")
        print("Hypothesis CONFIRMED: View is looking at wrong column (page_ranges) instead of derived mapping or physical file.")
    else:
        print("SUCCESS? Logic seems correct. Bug must be elsewhere.")

if __name__ == "__main__":
    test_page_count_retrieval()
