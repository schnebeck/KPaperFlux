
import unittest
import sqlite3
import os
from core.database import DatabaseManager
from core.document import Document

class TestLegacySchema(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_legacy_schema.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        
        self.db = DatabaseManager(self.db_path)
        self.db.init_db()
        
        # Insert a dummy document directly to ensure schema compliance
        self.uuid = "12345-uuid"
        self.db.connection.execute(
            """
            INSERT INTO documents (uuid, original_filename, text_content, created_at, page_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (self.uuid, "test.pdf", "Content", "2025-01-01 12:00:00", 1)
        )
        self.db.connection.commit()

    def tearDown(self):
        self.db.connection.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_get_document_by_uuid(self):
        """Test retrieving a document without legacy columns like doc_type, sender, etc."""
        doc = self.db.get_document_by_uuid(self.uuid)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.uuid, self.uuid)
        self.assertEqual(doc.original_filename, "test.pdf")
        
        # Verify legacy fields are None
        self.assertEqual(doc.doc_type, [])
        self.assertIsNone(doc.sender)
        self.assertIsNone(doc.amount)
        self.assertIsNone(doc.doc_date)
        
        # Verify Refined Physical Schema (Phase 99.2)
        self.assertIsNone(doc.tags)
        self.assertIsNone(doc.export_filename)
        
    def test_search_documents(self):
        """Test searching works with the new slim schema."""
        docs = self.db.search_documents("Content")
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].uuid, self.uuid)
        self.assertEqual(docs[0].doc_type, [])
        self.assertIsNone(docs[0].tags)

    def test_get_all_tags_with_counts(self):
        """Test tag aggregation (should ideally return empty or valid data, not crash)."""
        # This will crash if it looks for 'tags' column in documents
        tags = self.db.get_all_tags_with_counts()
        self.assertIsInstance(tags, dict)


if __name__ == "__main__":
    unittest.main()
