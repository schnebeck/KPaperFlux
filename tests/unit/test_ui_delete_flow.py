"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_ui_delete_flow.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Tests the soft/hard delete flow for virtual documents and
                verifies that orphan detection via get_by_source_file()
                correctly reflects which physical files can be purged.
------------------------------------------------------------------------------
"""

import unittest
import uuid
import datetime
from core.database import DatabaseManager
from core.repositories import LogicalRepository, PhysicalRepository
from core.models.physical import PhysicalFile
from core.models.virtual import VirtualDocument, SourceReference


class TestUIDeleteFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DatabaseManager(":memory:")
        self.db.init_db()
        self.logic_repo = LogicalRepository(self.db)
        self.phys_repo = PhysicalRepository(self.db)

        # Setup: 1 physical file, 2 virtual documents
        self.p_uuid = str(uuid.uuid4())
        phys = PhysicalFile(
            uuid=self.p_uuid,
            original_filename="test.pdf",
            file_path="/tmp/test.pdf",
            created_at=datetime.datetime.now().isoformat()
        )
        self.phys_repo.save(phys)

        v1 = VirtualDocument(uuid="ent1", source_mapping=[SourceReference(file_uuid=self.p_uuid, pages=[1], rotation=0)])
        self.logic_repo.save(v1)

        v2 = VirtualDocument(uuid="ent2", source_mapping=[SourceReference(file_uuid=self.p_uuid, pages=[2], rotation=0)])
        self.logic_repo.save(v2)

    def test_delete_flow(self) -> None:
        # 1. Active View
        active = self.db.get_all_entities_view()
        self.assertEqual(len(active), 2)

        # 2. Soft-delete ent1
        v1_loaded = self.logic_repo.get_by_uuid("ent1")
        v1_loaded.deleted = True
        self.logic_repo.save(v1_loaded)

        # 3. Active view shows only ent2
        active = self.db.get_all_entities_view()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].uuid, "ent2")

        # 4. Trash shows ent1
        trash = self.db.get_deleted_entities_view()
        self.assertEqual(len(trash), 1)
        self.assertEqual(trash[0].uuid, "ent1")

        # 5. Hard delete ent1; physical file still referenced by ent2
        self.logic_repo.delete_by_uuid("ent1")
        trash = self.db.get_deleted_entities_view()
        self.assertEqual(len(trash), 0)

        # 6. Physical file still referenced by ent2 — not yet an orphan
        refs = self.logic_repo.get_by_source_file(self.p_uuid)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].uuid, "ent2")

        # 7. Hard delete ent2 — physical file becomes an orphan
        v2_loaded = self.logic_repo.get_by_uuid("ent2")
        v2_loaded.deleted = True
        self.logic_repo.save(v2_loaded)
        self.logic_repo.delete_by_uuid("ent2")

        refs = self.logic_repo.get_by_source_file(self.p_uuid)
        self.assertEqual(refs, [], "Physical file should have no more references after all purges")


if __name__ == "__main__":
    unittest.main()
