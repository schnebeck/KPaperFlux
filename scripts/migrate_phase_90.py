
import sqlite3
import json
import sys
import os

DB_PATH = "kpaperflux.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Rename old table
        print("Renaming 'documents' to 'documents_old'...")
        cursor.execute("ALTER TABLE documents RENAME TO documents_old")
    except sqlite3.OperationalError as e:
        print(f"Rename failed (maybe already renamed?): {e}")
        # Check if documents_old exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents_old'")
        if not cursor.fetchone():
            print("Critical: documents_old does not exist and rename failed.")
            sys.exit(1)

    # 2. Create NEW Dictionary Table
    print("Creating new 'documents' table...")
    create_sql = """
    CREATE TABLE IF NOT EXISTS documents (
        uuid TEXT PRIMARY KEY,
        doc_type TEXT,            -- JSON List: ["Invoice", "Contract"]
        original_filename TEXT,
        export_filename TEXT,
        page_count INTEGER,
        created_at TEXT,
        last_processed_at TEXT,
        locked INTEGER DEFAULT 0,
        deleted INTEGER DEFAULT 0, -- New Column
        tags TEXT,                -- CSV String (Legacy compat)
        
        text_content TEXT,        -- System: FTS
        phash TEXT,              -- System: Dedup
        semantic_data TEXT,       -- System: Source of Truth (JSON)
        extra_data TEXT,          -- Legacy: Merge candidate? Keeping for now to be safe.
        
        -- Virtual Columns for Indexing
        v_sender TEXT GENERATED ALWAYS AS (json_extract(semantic_data, '$.summary.sender_name')) VIRTUAL,
        v_doc_date TEXT GENERATED ALWAYS AS (json_extract(semantic_data, '$.summary.main_date')) VIRTUAL,
        v_amount REAL GENERATED ALWAYS AS (json_extract(semantic_data, '$.summary.amount')) VIRTUAL
    )
    """
    cursor.execute(create_sql)

    # 3. Migrate Data
    print("Migrating data...")
    cursor.execute("SELECT uuid, doc_type, original_filename, export_filename, page_count, created_at, last_processed_at, locked, tags, text_content, phash, semantic_data, extra_data FROM documents_old")
    rows = cursor.fetchall()

    inserted_count = 0
    for row in rows:
        uuid, old_type, orig_name, exp_name, pages, created, updated, locked, tags, text, phash, semantic, extra = row
        
        # Transform DocType -> JSON List
        new_type_list = []
        if old_type:
            new_type_list.append(old_type)
        new_type_json = json.dumps(new_type_list) # e.g. '["Invoice"]'

        # Insert
        insert_sql = """
        INSERT INTO documents (
            uuid, doc_type, original_filename, export_filename, page_count, 
            created_at, last_processed_at, locked, deleted, tags, 
            text_content, phash, semantic_data, extra_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
        """
        
        cursor.execute(insert_sql, (
            uuid, new_type_json, orig_name, exp_name, pages, 
            created, updated, locked, tags, 
            text, phash, semantic, extra
        ))
        inserted_count += 1

    conn.commit()
    print(f"Migration complete. {inserted_count} documents migrated.")
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM documents")
    new_count = cursor.fetchone()[0]
    print(f"New table count: {new_count}")
    
    conn.close()

if __name__ == "__main__":
    migrate()
