
import os
import sqlite3
import json
from core.database import DatabaseManager

db_path = "/home/schnebeck/.local/share/kpaperflux/kpaperflux.db"
uuid = "f51049bf-27e9-452f-9b49-bb742cb62409"

db = DatabaseManager(db_path)
doc = db.get_document_by_uuid(uuid)

if doc:
    print(f"UUID: {doc.uuid}")
    print(f"Type Tags: {doc.type_tags}")
    print(f"Status: {doc.status}")
    print(f"Sender Name: {doc.sender_name}")
    print(f"IBAN: {doc.iban}")
    print(f"BIC: {doc.bic}")
    print(f"Total Amount: {doc.total_amount}")
    print(f"Doc Number: {doc.doc_number}")
    
    is_financial = any(t in ["INVOICE", "RECEIPT", "UTILITY_BILL"] for t in (doc.type_tags or []))
    print(f"Is Financial: {is_financial}")
    
    if doc.semantic_data:
        print("Semantic Data Present")
        print(f"Bodies keys: {list(doc.semantic_data.bodies.keys())}")
        fb = doc.semantic_data.bodies.get("finance_body")
        if fb:
            print(f"Finance Body Type: {type(fb)}")
            if hasattr(fb, "total_gross"):
                print(f"Total Gross (attr): {fb.total_gross}")
            elif isinstance(fb, dict):
                print(f"Total Gross (dict): {fb.get('total_gross')}")
else:
    print("Document not found")
