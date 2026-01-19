import unittest
from core.database import DatabaseManager, Document

class TestSearchAbstraction(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.init_db()
        
        # Setup: 1 Doc, 1 Entity
        doc = Document(uuid="doc1", original_filename="test.pdf", file_path="/tmp/test.pdf", file_size=100)
        self.db.insert_document(doc)
        
        # Insert Entity with specific metadata (doc_type, sender)
        self.db.connection.execute(
            """INSERT INTO semantic_entities 
               (entity_uuid, source_doc_uuid, doc_type, sender_name, deleted, status, doc_date) 
               VALUES (?, ?, ?, ?, 0, 'NEW', '2023-01-01')""",
            ("ent1", "doc1", "INVOICE", "MySender")
        )
        # Init ref count
        self.db.connection.execute("UPDATE documents SET ref_count = 1 WHERE uuid = 'doc1'")

    def test_search_returns_entity_data(self):
        """
        Verify that search_documents_advanced returns full Entity data (e.g. sender, doc_type),
        matching get_all_entities_view.
        """
        # 1. Base View (Correct)
        base_view = self.db.get_all_entities_view()
        self.assertEqual(len(base_view), 1)
        # Document model normalizes doc_type to list
        self.assertEqual(base_view[0].doc_type, ["INVOICE"]) 
        self.assertEqual(base_view[0].sender, "MySender")
        
        # 2. Search View (The Problematic One)
        # Empty query "Clear All" should return same data as base view
        search_results = self.db.search_documents_advanced({})
        
        self.assertEqual(len(search_results), 1, "Search should find the document")
        
        # Check if Metadata is present
        # Fails if search queries 'documents' table which no longer has doc_type/sender
        print(f"Search Result DocType: {search_results[0].doc_type}")
        print(f"Search Result Sender: {search_results[0].sender}")
        
        self.assertEqual(search_results[0].doc_type, ["INVOICE"], "Search result missing doc_type (Data Layer Mismatch)")
        self.assertEqual(search_results[0].sender, "MySender", "Search result missing sender")
        self.assertEqual(search_results[0].uuid, "ent1", "Search should return Entity UUID, not Doc UUID")

if __name__ == '__main__':
    unittest.main()
