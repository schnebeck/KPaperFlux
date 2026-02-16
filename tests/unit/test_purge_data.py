
import os
import pytest
from core.database import DatabaseManager

def test_purge_all_data_destructive(tmp_path):
    # Setup database file
    db_file = str(tmp_path / "purge_test.db")
    db = DatabaseManager(db_file)
    
    # 1. Insert some dummy data
    cursor = db.connection.cursor()
    cursor.execute("INSERT INTO physical_files (uuid) VALUES (?)", ("phys-1",))
    cursor.execute("INSERT INTO virtual_documents (uuid, status) VALUES (?, ?)", ("virt-1", "PROCESSED"))
    db.connection.commit()
    
    # Verify data exists
    cursor.execute("SELECT COUNT(*) FROM physical_files")
    assert cursor.fetchone()[0] == 1
    
    # 2. Perform DESTRUCTIVE Purge
    # (No vault path for this simple test)
    success = db.purge_all_data(vault_path=None)
    assert success is True
    
    # 3. Verify Database File was replaced and re-initialized
    assert os.path.exists(db_file)
    
    # New cursor/connection inside DatabaseManager should be fresh
    cursor = db.connection.cursor()
    
    # Table must be empty but exist
    cursor.execute("SELECT COUNT(*) FROM physical_files")
    assert cursor.fetchone()[0] == 0
    
    # Verify new schema is applied correctly (checking one of the new columns)
    cursor.execute("PRAGMA table_info(virtual_documents)")
    cols = [row['name'] for row in cursor.fetchall()]
    assert "archived" in cols
    assert "pdf_class" in cols 
