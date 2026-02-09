
import os
import sys
import shutil
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.config import AppConfig
from core.database import DatabaseManager
from core.vault import DocumentVault
from core.pipeline import PipelineProcessor
from core.models.virtual import VirtualDocument

def smoke_test_import():
    print("=== Starting Smoke Test: Import (V2) ===")
    
    # 1. Setup Temporary Environment
    test_root = Path("devel/smoke_env")
    if test_root.exists():
        shutil.rmtree(test_root)
    test_root.mkdir(parents=True)
    
    vault_path = test_root / "vault"
    db_path = test_root / "test.db"
    
    print(f"Creating test vault at: {vault_path}")
    vault = DocumentVault(base_path=str(vault_path))
    
    print(f"Initializing test database at: {db_path}")
    db = DatabaseManager(db_path=str(db_path))
    db.init_db()
    
    pipeline = PipelineProcessor(vault=vault, db=db)
    
    # 2. Source File
    source_file = Path("devel/smoke_data/test.pdf")
    if not source_file.exists():
        print("Error: test.pdf not found. Run command to create it first.")
        return False
    
    print(f"Importing document: {source_file}")
    
    # 3. Execute Import
    try:
        # Pipeline returns the VirtualDocument (V2)
        v_doc = pipeline.process_document(str(source_file))
        
        if not v_doc:
            print("[FAIL] Pipeline returned None")
            return False
        
        print(f"[SUCCESS] Pipeline returned VirtualDocument with UUID: {v_doc.uuid}")
        print(f"Status: {v_doc.status}")
        
        # 4. Verify Database
        db_doc = db.get_document_by_uuid(v_doc.uuid)
        if not db_doc:
            print("[FAIL] Document not found in database after import")
            return False
        
        print(f"[SUCCESS] Document verified in database. Status: {db_doc.status}")
        
        # 5. Verify Vault
        if not v_doc.source_mapping:
            print("[FAIL] No source mapping found in VirtualDocument")
            return False
            
        phys_uuid = v_doc.source_mapping[0].file_uuid
        phys_path = vault.get_file_path(phys_uuid)
        if not os.path.exists(phys_path):
            print(f"[FAIL] Physical file not found in vault: {phys_path}")
            return False
            
        print(f"[SUCCESS] Physical file found in vault: {phys_path}")
        
        print("\n=== Smoke Test PASSED ===")
        return True
        
    except Exception as e:
        print(f"[ERROR] Import failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = smoke_test_import()
    sys.exit(0 if success else 1)
