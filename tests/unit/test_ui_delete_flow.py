import unittest
import sqlite3
import json
from core.database import DatabaseManager, Document

class TestUIDeleteFlow(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.init_db()
        
        # Setup: 1 Doc, 2 Entities
        doc = Document(uuid="doc1", original_filename="test.pdf", file_path="/tmp/test.pdf", file_hash="123", file_size=100)
        self.db.insert_document(doc)
        
        # New behavior: insert_document creates a default entity.
        # This test manually creates 2 specific entities and expects only 2.
        # Remove the auto-created one to match expected state.
        self.db.connection.execute("DELETE FROM semantic_entities WHERE source_doc_uuid = 'doc1'")
        
        # Entity 1
        self.db.connection.execute(
            "INSERT INTO semantic_entities (entity_uuid, source_doc_uuid, doc_type, deleted) VALUES (?, ?, ?, 0)",
            ("ent1", "doc1", "INVOICE")
        )
        self.db.connection.execute("UPDATE documents SET ref_count = ref_count + 1 WHERE uuid = 'doc1'")
        
        # Entity 2
        self.db.connection.execute(
            "INSERT INTO semantic_entities (entity_uuid, source_doc_uuid, doc_type, deleted) VALUES (?, ?, ?, 0)",
            ("ent2", "doc1", "RECEIPT")
        )
        self.db.connection.execute("UPDATE documents SET ref_count = ref_count + 1 WHERE uuid = 'doc1'")

    def test_delete_flow(self):
        # 1. Active View
        active = self.db.get_all_entities_view()
        self.assertEqual(len(active), 2, "Should have 2 active entities")
        self.assertTrue(any(d.uuid == "ent1" for d in active))
        self.assertTrue(any(d.uuid == "ent2" for d in active))
        
        # 2. Delete ent1
        self.db.delete_entity("ent1")
        
        # 3. Verify Active View (Crucial Fix Check)
        active = self.db.get_all_entities_view()
        self.assertEqual(len(active), 1, "Should have 1 active entity after delete")
        self.assertEqual(active[0].uuid, "ent2")
        
        # 4. Verify Trash View
        trash = self.db.get_deleted_entities_view()
        self.assertEqual(len(trash), 1, "Should have 1 entity in trash")
        self.assertEqual(trash[0].uuid, "ent1")
        
        # 5. Purge Trash
        self.db.purge_entity("ent1")
        
        # 6. Verify Trash Empty
        trash = self.db.get_deleted_entities_view()
        self.assertEqual(len(trash), 0)
        
        # 7. Purge ent2 (Last One)
        self.db.delete_entity("ent2")
        self.db.purge_entity("ent2")
        
        # 8. Verify Source Doc Deleted
        cursor = self.db.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        self.assertEqual(cursor.fetchone()[0], 0, "Source document should be deleted")

if __name__ == '__main__':
    unittest.main()
