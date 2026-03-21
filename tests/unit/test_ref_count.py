"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_ref_count.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Tests for physical file orphan detection. Verifies that
                get_by_source_file correctly identifies active references
                to a physical file, which is the mechanism used by
                physical_cleanup() to decide whether to delete a file.
------------------------------------------------------------------------------
"""

import unittest
import uuid
import datetime
from core.database import DatabaseManager
from core.repositories import LogicalRepository, PhysicalRepository
from core.models.physical import PhysicalFile
from core.models.virtual import VirtualDocument, SourceReference


class TestOrphanDetection(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DatabaseManager(":memory:")
        self.db.init_db()
        self.phys_repo = PhysicalRepository(self.db)
        self.logic_repo = LogicalRepository(self.db)

    def test_physical_file_referenced_by_virtual_doc(self) -> None:
        """A physical file with an active virtual document is not an orphan."""
        p_uuid = str(uuid.uuid4())
        phys = PhysicalFile(
            uuid=p_uuid,
            original_filename="ref_test.pdf",
            file_path="/tmp/test.pdf",
            created_at=datetime.datetime.now().isoformat()
        )
        self.phys_repo.save(phys)

        v_uuid = str(uuid.uuid4())
        v_doc = VirtualDocument(
            uuid=v_uuid,
            created_at=phys.created_at,
            source_mapping=[SourceReference(file_uuid=p_uuid, pages=[1], rotation=0)]
        )
        self.logic_repo.save(v_doc)

        referencing = self.logic_repo.get_by_source_file(p_uuid)
        self.assertEqual(len(referencing), 1)
        self.assertEqual(referencing[0].uuid, v_uuid)

    def test_physical_file_becomes_orphan_after_hard_delete(self) -> None:
        """After the only referencing virtual doc is hard-deleted, get_by_source_file returns empty."""
        p_uuid = str(uuid.uuid4())
        phys = PhysicalFile(
            uuid=p_uuid,
            original_filename="orphan_test.pdf",
            file_path="/tmp/orphan.pdf",
            created_at=datetime.datetime.now().isoformat()
        )
        self.phys_repo.save(phys)

        v_uuid = str(uuid.uuid4())
        v_doc = VirtualDocument(
            uuid=v_uuid,
            created_at=phys.created_at,
            source_mapping=[SourceReference(file_uuid=p_uuid, pages=[1], rotation=0)]
        )
        self.logic_repo.save(v_doc)
        self.logic_repo.delete_by_uuid(v_uuid)

        referencing = self.logic_repo.get_by_source_file(p_uuid)
        self.assertEqual(referencing, [])

    def test_physical_file_not_orphaned_by_soft_delete(self) -> None:
        """Soft-deleting a virtual doc (deleted=1) does NOT make its physical file an orphan."""
        p_uuid = str(uuid.uuid4())
        phys = PhysicalFile(
            uuid=p_uuid,
            original_filename="soft_delete_test.pdf",
            file_path="/tmp/soft.pdf",
            created_at=datetime.datetime.now().isoformat()
        )
        self.phys_repo.save(phys)

        v_uuid = str(uuid.uuid4())
        v_doc = VirtualDocument(
            uuid=v_uuid,
            created_at=phys.created_at,
            source_mapping=[SourceReference(file_uuid=p_uuid, pages=[1], rotation=0)]
        )
        self.logic_repo.save(v_doc)
        self.logic_repo.mark_deleted(v_uuid, True)

        # Soft-deleted docs are still in the DB and still reference the physical file.
        # physical_cleanup() is only called on purge, so soft-deleted docs preserve physical files.
        referencing = self.logic_repo.get_by_source_file(p_uuid)
        self.assertEqual(len(referencing), 1)

    def test_no_ref_count_column_on_physical_file(self) -> None:
        """The physical_files table must not contain a ref_count column."""
        cursor = self.db.connection.cursor()
        cursor.execute("PRAGMA table_info(physical_files)")
        columns = [row["name"] for row in cursor.fetchall()]
        self.assertNotIn("ref_count", columns)


if __name__ == "__main__":
    unittest.main()
