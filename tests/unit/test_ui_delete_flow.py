import unittest
import uuid
import datetime
from core.database import DatabaseManager
from core.repositories import LogicalRepository, PhysicalRepository
from core.models.physical import PhysicalFile
from core.models.virtual import VirtualDocument, SourceReference

class TestUIDeleteFlow(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.init_db()
        self.logic_repo = LogicalRepository(self.db)
        self.phys_repo = PhysicalRepository(self.db)
        
        # Setup: 1 Doc, 2 Entities
        p_uuid = str(uuid.uuid4())
        phys = PhysicalFile(
            uuid=p_uuid,
            original_filename="test.pdf",
            file_path="/tmp/test.pdf",
            created_at=datetime.datetime.now().isoformat()
        )
        self.phys_repo.save(phys)
        
        # Entity 1
        v1 = VirtualDocument(uuid="ent1", source_mapping=[SourceReference(file_uuid=p_uuid, pages=[1], rotation=0)])
        self.logic_repo.save(v1)
        
        # Entity 2
        v2 = VirtualDocument(uuid="ent2", source_mapping=[SourceReference(file_uuid=p_uuid, pages=[2], rotation=0)])
        self.logic_repo.save(v2)
        
        # Triggers now handle incrementing ref_count automatically.
        # Initial save of v1 and v2 should make it 2.

    def test_delete_flow(self):
        # 1. Active View
        active = self.db.get_all_entities_view()
        self.assertEqual(len(active), 2, "Should have 2 active entities")
        
        # 2. Delete ent1 (Soft)
        v1_loaded = self.logic_repo.get_by_uuid("ent1")
        v1_loaded.deleted = True
        self.logic_repo.save(v1_loaded)
        
        # 3. Verify Active View
        active = self.db.get_all_entities_view()
        self.assertEqual(len(active), 1, "Should have 1 active entity after delete")
        self.assertEqual(active[0].uuid, "ent2")
        
        # 4. Verify Trash View
        trash = self.db.get_deleted_entities_view()
        self.assertEqual(len(trash), 1, "Should have 1 entity in trash")
        self.assertEqual(trash[0].uuid, "ent1")
        
        # 5. Purge Trash (Hard Delete)
        self.logic_repo.delete_by_uuid("ent1")
        
        # 6. Verify Trash Empty
        trash = self.db.get_deleted_entities_view()
        self.assertEqual(len(trash), 0)
        
        # 7. Verify ref_count is 1 (ent2 still exists)
        cursor = self.db.connection.cursor()
        cursor.execute("SELECT ref_count FROM physical_files")
        self.assertEqual(cursor.fetchone()[0], 1, "Ref count should be 1 after one purge")

        # 8. Purge ent2 (Last One: Soft -> Hard)
        v2_loaded = self.logic_repo.get_by_uuid("ent2")
        v2_loaded.deleted = True
        self.logic_repo.save(v2_loaded)
        self.logic_repo.delete_by_uuid("ent2")
        
        # 9. Verify Ref Count is 0
        cursor.execute("SELECT ref_count FROM physical_files")
        self.assertEqual(cursor.fetchone()[0], 0, "Ref count should be 0 after all purges")

if __name__ == '__main__':
    unittest.main()
