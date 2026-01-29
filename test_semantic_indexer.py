import sqlite3
import json
import time

def test_indexer_update():
    print("Testing Semantic Indexer Auto-Update...")
    
    conn = sqlite3.connect("kpaperflux.db")
    try:
        # 1. Get a test document
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT uuid, semantic_data FROM virtual_documents LIMIT 1")
        except Exception as e:
            print(f"Error accessing tables: {e}")
            return

        row = cursor.fetchone()
        
        if not row:
            print("No documents found.")
            return
            
        uuid, raw_json = row
        print(f"Testing on Document {uuid}...")
        
        # 2. Parse and Update Semantic Data
        data = json.loads(raw_json) if raw_json else {"summary": {}}
        if "summary" not in data: data["summary"] = {}
        
        # Set Test Values
        test_sender = f"Test Sender {int(time.time())}"
        test_amount = 123.456
        
        data["summary"]["sender_name"] = test_sender
        data["summary"]["amount"] = test_amount
        
        new_json = json.dumps(data)
        
        # 3. Update DB
        print(f"Updating semantic_data with sender='{test_sender}'...")
        cursor.execute("UPDATE virtual_documents SET semantic_data = ? WHERE uuid = ?", (new_json, uuid))
        conn.commit()
        
        # 4. Read back Virtual Columns
        cursor.execute("SELECT sender, amount FROM virtual_documents WHERE uuid = ?", (uuid,))
        res = cursor.fetchone()
        v_sender, v_amount = res
        
        print(f"v_sender: {v_sender}")
        print(f"v_amount: {v_amount}")
        
        # 5. Verify
        if v_sender == test_sender and float(v_amount) == test_amount:
            print("SUCCESS: Virtual Columns updated properly!")
        else:
            print(f"FAILURE: Expected {test_sender}/{test_amount}, got {v_sender}/{v_amount}")
    finally:
        conn.close()

if __name__ == "__main__":
    test_indexer_update()
