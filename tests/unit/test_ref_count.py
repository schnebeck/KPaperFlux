import unittest
import os
import sqlite3
import json
from core.database import DatabaseManager, Document

class TestRefCount(unittest.TestCase):
    def setUp(self):
        self.db_path = ":memory:" # Use in-memory DB for speed
        self.db = DatabaseManager(self.db_path)
        self.db.init_db()

    def test_ref_count_lifecycle(self):
        """Test the full lifecycle of ref counting: Create, Soft Delete, Purge."""
        
        # 1. Create Source Document (Mock)
        doc = Document(uuid="doc1", file_path="/tmp/doc1.pdf", original_filename="doc1.pdf", file_hash="abc", file_size=1024)
        self.db.insert_document(doc)
        
        # FIX: insert_document creates a default semantic entity.
        # This interferes with the manual ref counting test.
        # Remove the auto-created entity to start with 0 refs.
        self.db.connection.execute("DELETE FROM semantic_entities WHERE source_doc_uuid = 'doc1'")
        self.db.connection.execute("UPDATE documents SET ref_count = 0 WHERE uuid = 'doc1'")
        
        # Verify initial refs (0)
        cursor = self.db.connection.cursor()
        cursor.execute("SELECT ref_count FROM documents WHERE uuid = 'doc1'")
        self.assertEqual(cursor.fetchone()[0], 0, "Initial ref count should be 0")
        
        # 2. Add Entities (Simulate Canonizer)
        # Manually insert entities since Canonizer is higher level
        # Trigger increment manually as Canonizer does
        
        # Entity 1
        self.db.connection.execute(
            "INSERT INTO semantic_entities (entity_uuid, source_doc_uuid, doc_type, status) VALUES (?, ?, ?, ?)",
            ("ent1", "doc1", "INVOICE", "NEW")
        )
        self.db.connection.execute("UPDATE documents SET ref_count = ref_count + 1 WHERE uuid = 'doc1'")
        
        # Entity 2
        self.db.connection.execute(
            "INSERT INTO semantic_entities (entity_uuid, source_doc_uuid, doc_type, status) VALUES (?, ?, ?, ?)",
            ("ent2", "doc1", "RECEIPT", "NEW")
        )
        self.db.connection.execute("UPDATE documents SET ref_count = ref_count + 1 WHERE uuid = 'doc1'")
        
        cursor.execute("SELECT ref_count FROM documents WHERE uuid = 'doc1'")
        self.assertEqual(cursor.fetchone()[0], 2, "Ref count should be 2")
        
        # 3. Soft Delete Entity 1
        success = self.db.delete_entity("ent1")
        self.assertTrue(success)
        
        # Verify Ref Count Unchanged (Soft Delete)
        cursor.execute("SELECT ref_count FROM documents WHERE uuid = 'doc1'")
        self.assertEqual(cursor.fetchone()[0], 2, "Ref count should still be 2 after soft delete")
        
        # Verify Trash Bin
        trash = self.db.get_deleted_entities_view()
        self.assertEqual(len(trash), 1)
        self.assertEqual(trash[0].uuid, "ent1")
        
        # 4. Purge Entity 1 (Hard Delete)
        success = self.db.purge_entity("ent1")
        self.assertTrue(success)
        
        # Verify Ref Count Decremented
        cursor.execute("SELECT ref_count FROM documents WHERE uuid = 'doc1'")
        self.assertEqual(cursor.fetchone()[0], 1, "Ref count should be 1 after purge")
        
        # Verify Trash Bin Empty
        trash = self.db.get_deleted_entities_view()
        self.assertEqual(len(trash), 0)
        
        # 5. Purge Entity 2 (Last One)
        success = self.db.purge_entity("ent2")
        self.assertTrue(success)
        
        # Verify Document Deleted
        cursor.execute("SELECT COUNT(*) FROM documents WHERE uuid = 'doc1'")
        self.assertEqual(cursor.fetchone()[0], 0, "Source Document should be deleted after last entity purge")

if __name__ == '__main__':
    unittest.main()
