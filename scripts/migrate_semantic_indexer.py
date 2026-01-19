import sqlite3
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

DB_PATH = "kpaperflux.db"

def migrate_db():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Check existing columns
    cursor.execute("PRAGMA table_info(documents)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns: {columns}")
    
    # Define Virtual Columns
    # Note: SQLite 3.31+ required for GENERATED ALWAYS AS
    virtual_columns = [
        ("v_sender", "TEXT", "json_extract(semantic_data, '$.summary.sender_name')"),
        ("v_doc_date", "TEXT", "json_extract(semantic_data, '$.summary.main_date')"),
        ("v_amount", "REAL", "json_extract(semantic_data, '$.summary.amount')")
    ]
    
    for col_name, col_type, expr in virtual_columns:
        if col_name in columns:
            print(f"Skipping {col_name} (already exists)")
        else:
            print(f"Adding Generated Column: {col_name}...")
            try:
                # Syntax: GENERATED ALWAYS AS (expr) STORED|VIRTUAL
                # VIRTUAL is default and saves space (computed on read)
                # STORED saves CPU (computed on write) -> Good for indexing!
                try:
                     print(f"Attempting STORED for {col_name}...")
                     sql = f"ALTER TABLE documents ADD COLUMN {col_name} {col_type} GENERATED ALWAYS AS ({expr}) STORED"
                     conn.execute(sql)
                     print(f"Success (STORED): {col_name}")
                except sqlite3.OperationalError:
                     print(f"STORED failed, attempting VIRTUAL for {col_name}...")
                     sql = f"ALTER TABLE documents ADD COLUMN {col_name} {col_type} GENERATED ALWAYS AS ({expr}) VIRTUAL"
                     conn.execute(sql)
                     print(f"Success (VIRTUAL): {col_name}")

            except sqlite3.OperationalError as e:
                print(f"Error adding {col_name}: {e}")
                print("Your SQLite version might be too old for GENERATED COLUMNS.")
                return

    conn.commit()
    conn.close()
    print("Migration Complete.")

if __name__ == "__main__":
    migrate_db()
