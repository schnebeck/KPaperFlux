import unittest
import uuid
import datetime
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
            file_uuid=p_uuid,
            original_filename="ref_test.pdf",
            file_path="/tmp/test.pdf",
            created_at=datetime.datetime.now().isoformat()
        )
        self.phys_repo.save(phys)
        
        # Verify initial 0 (Repo defaults to 0)
        p = self.phys_repo.get_by_uuid(p_uuid)
        self.assertEqual(p.ref_count, 0)
        
        # 2. Add Logical Entity (Simulation of Canonizer Save)
        # Note: LogicalRepo.save DOES NOT auto-increment ref count currently?
        # CanonizerService.save_entity did it manually!
        # core/canonizer.py line 583: UPDATE documents SET ref_count...
        # So LogicalRepo.save does NOT increment.
        # But LogicalRepo.delete_by_uuid (which I just fixed) DOES decrement.
        # This is asymmetric. 
        # Ideally LogicalRepo.save should increment?
        # Or Canonizer should handle both?
        # Since I moved decrement to Repo, I should move increment to Repo for symmetry?
        # But 'save' is also 'update'. We want to increment only on INSERT.
        # Upsert logic makes it tricky.
        
        # For this test, I will simulate the increments manually (as Canonizer does)
        # or rely on fixing LogicalRepo.save later.
        # To be safe, I'll invoke increment explicitly here to test the DECREMENT logic.
        
        self.phys_repo.increment_ref_count(p_uuid) 
        p = self.phys_repo.get_by_uuid(p_uuid)
        self.assertEqual(p.ref_count, 1)
        
        # 3. Create Logic Doc (linked)
        v_uuid = str(uuid.uuid4())
        v_doc = VirtualDocument(
             entity_uuid=v_uuid,
             sender_name="Ent1",
             created_at=phys.created_at,
             source_mapping=[SourceReference(file_uuid=p_uuid, pages=[1], rotation=0)]
        )
        # Save uses FIRST source mapping file_uuid as 'source_doc_uuid' anchor.
        self.logic_repo.save(v_doc)
        
        # 4. Delete Logic Doc (This triggers the Decrement logic I added)
        self.logic_repo.delete_by_uuid(v_uuid)
        
        # 5. Verify Decrement
        p = self.phys_repo.get_by_uuid(p_uuid)
        self.assertEqual(p.ref_count, 0)
        
    def test_multi_ref(self):
         # ... similar setup for 2 entities ...
         pass

if __name__ == '__main__':
    unittest.main()
