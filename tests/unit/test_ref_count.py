import unittest
import uuid
import datetime
import sqlite3
from core.database import DatabaseManager
from core.repositories import LogicalRepository, PhysicalRepository
from core.models.physical import PhysicalFile
from core.models.virtual import VirtualDocument, SourceReference

class TestRefCount(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.init_db()
        self.phys_repo = PhysicalRepository(self.db)
        self.logic_repo = LogicalRepository(self.db)

    def test_ref_count_lifecycle(self):
        """Test ref counting: create physical, create logic (inc), delete logic (dec)."""
        
        # 1. Create Physical File
        p_uuid = str(uuid.uuid4())
        phys = PhysicalFile(
            uuid=p_uuid,
            original_filename="ref_test.pdf",
            file_path="/tmp/test.pdf",
            created_at=datetime.datetime.now().isoformat()
        )
        self.phys_repo.save(phys)
        
        # Verify initial 0
        p = self.phys_repo.get_by_uuid(p_uuid)
        print(f"DEBUG: Initial ref_count for {p_uuid}: {p.ref_count}")
        self.assertEqual(p.ref_count, 0)
        
        # 2. Add Logical Entity (triggers ref_count increment)
        v_uuid = str(uuid.uuid4())
        v_doc = VirtualDocument(
             uuid=v_uuid,
             created_at=phys.created_at,
             source_mapping=[SourceReference(file_uuid=p_uuid, pages=[1], rotation=0)]
        )
        print(f"DEBUG: Saving logic doc {v_uuid} with mapping to {p_uuid}")
        self.logic_repo.save(v_doc)
        
        # Verify Increment via Trigger
        p = self.phys_repo.get_by_uuid(p_uuid)
        print(f"DEBUG: ref_count after save: {p.ref_count}")
        
        if p.ref_count == 0:
            cursor = self.db.connection.cursor()
            cursor.execute("SELECT uuid, source_mapping FROM virtual_documents")
            v_rows = cursor.fetchall()
            print(f"DEBUG: virtual_documents rows: {len(v_rows)}")
            if v_rows:
                print(f"DEBUG: row[1] (mapping): {v_rows[0][1]}")
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
            print(f"DEBUG: Triggers: {[r[0] for r in cursor.fetchall()]}")

        self.assertEqual(p.ref_count, 1)
        
        # 3. Delete Logic Doc (triggers ref_count decrement)
        self.logic_repo.delete_by_uuid(v_uuid)
        
        # 4. Verify Decrement via Trigger
        p = self.phys_repo.get_by_uuid(p_uuid)
        print(f"DEBUG: ref_count after delete: {p.ref_count}")
        self.assertEqual(p.ref_count, 0)

if __name__ == '__main__':
    unittest.main()
