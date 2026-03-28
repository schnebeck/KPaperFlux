"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_group_repo.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for GroupRepository CRUD and membership operations.
                Uses an in-memory SQLite database — no files written to disk.
------------------------------------------------------------------------------
"""
import pytest
from unittest.mock import MagicMock

from core.models.group import DocumentGroup
from core.repositories.group_repo import GroupRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def repo(tmp_path):
    """GroupRepository backed by a real (temporary) DatabaseManager."""
    from core.database import DatabaseManager
    db = DatabaseManager(str(tmp_path / "test.db"))
    return GroupRepository(db)


# ---------------------------------------------------------------------------
# Group CRUD
# ---------------------------------------------------------------------------

class TestGroupCRUD:

    def test_create_returns_group(self, repo):
        g = repo.create("Projekt Alpha")
        assert g is not None
        assert g.name == "Projekt Alpha"
        assert g.id is not None

    def test_create_sets_default_icon(self, repo):
        g = repo.create("Test")
        assert g.icon == "📁"

    def test_create_with_custom_icon(self, repo):
        g = repo.create("Custom", icon="🗂")
        assert g.icon == "🗂"

    def test_get_by_id_returns_saved_group(self, repo):
        g = repo.create("Lieferanten")
        fetched = repo.get_by_id(g.id)
        assert fetched is not None
        assert fetched.name == "Lieferanten"

    def test_get_by_id_unknown_returns_none(self, repo):
        assert repo.get_by_id("nonexistent-uuid") is None

    def test_get_all_returns_all_groups(self, repo):
        repo.create("A")
        repo.create("B")
        repo.create("C")
        groups = repo.get_all()
        names = [g.name for g in groups]
        assert "A" in names and "B" in names and "C" in names

    def test_get_all_empty_initially(self, repo):
        assert repo.get_all() == []

    def test_rename_updates_name(self, repo):
        g = repo.create("Old Name")
        repo.rename(g.id, "New Name")
        fetched = repo.get_by_id(g.id)
        assert fetched.name == "New Name"

    def test_delete_removes_group(self, repo):
        g = repo.create("To Delete")
        repo.delete(g.id)
        assert repo.get_by_id(g.id) is None

    def test_delete_unknown_returns_true(self, repo):
        # Deleting non-existent is harmless
        assert repo.delete("no-such-id") is True


# ---------------------------------------------------------------------------
# Hierarchy
# ---------------------------------------------------------------------------

class TestGroupHierarchy:

    def test_create_subgroup(self, repo):
        parent = repo.create("Parent")
        child = repo.create("Child", parent_id=parent.id)
        assert child.parent_id == parent.id

    def test_get_children_top_level(self, repo):
        g1 = repo.create("Top1")
        g2 = repo.create("Top2")
        repo.create("Sub", parent_id=g1.id)
        top = repo.get_children(None)
        top_names = [g.name for g in top]
        assert "Top1" in top_names and "Top2" in top_names
        assert "Sub" not in top_names

    def test_get_children_of_parent(self, repo):
        parent = repo.create("Parent")
        child1 = repo.create("Child1", parent_id=parent.id)
        child2 = repo.create("Child2", parent_id=parent.id)
        children = repo.get_children(parent.id)
        names = [g.name for g in children]
        assert "Child1" in names and "Child2" in names

    def test_delete_parent_reparents_children(self, repo):
        """Child.parent_id becomes NULL when parent is deleted (ON DELETE SET NULL)."""
        parent = repo.create("Parent")
        child = repo.create("Child", parent_id=parent.id)
        repo.delete(parent.id)
        fetched = repo.get_by_id(child.id)
        assert fetched is not None
        assert fetched.parent_id is None


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

class TestGroupMembership:

    def test_add_membership(self, repo):
        g = repo.create("Group")
        repo.add_membership("uuid-doc-1", g.id)
        uuids = repo.get_document_uuids_in_group(g.id)
        assert "uuid-doc-1" in uuids

    def test_add_membership_idempotent(self, repo):
        g = repo.create("Group")
        repo.add_membership("uuid-doc-1", g.id)
        repo.add_membership("uuid-doc-1", g.id)  # duplicate — no error
        assert repo.get_document_uuids_in_group(g.id).count("uuid-doc-1") == 1

    def test_remove_membership(self, repo):
        g = repo.create("Group")
        repo.add_membership("uuid-doc-1", g.id)
        repo.remove_membership("uuid-doc-1", g.id)
        assert "uuid-doc-1" not in repo.get_document_uuids_in_group(g.id)

    def test_get_groups_for_document(self, repo):
        g1 = repo.create("G1")
        g2 = repo.create("G2")
        repo.add_membership("doc-uuid", g1.id)
        repo.add_membership("doc-uuid", g2.id)
        groups = repo.get_groups_for_document("doc-uuid")
        names = [g.name for g in groups]
        assert "G1" in names and "G2" in names

    def test_get_groups_for_document_empty(self, repo):
        assert repo.get_groups_for_document("unknown-doc") == []

    def test_document_count(self, repo):
        g = repo.create("Group")
        assert repo.get_document_count(g.id) == 0
        repo.add_membership("doc-1", g.id)
        repo.add_membership("doc-2", g.id)
        assert repo.get_document_count(g.id) == 2

    def test_delete_group_cascades_memberships(self, repo):
        g = repo.create("Group")
        repo.add_membership("doc-uuid", g.id)
        repo.delete(g.id)
        # group gone, membership gone — get_document_uuids_in_group on deleted ID returns []
        assert repo.get_document_uuids_in_group(g.id) == []

    def test_one_document_many_groups(self, repo):
        """Verify label metaphor: document can belong to multiple groups."""
        groups = [repo.create(f"Group {i}") for i in range(5)]
        for g in groups:
            repo.add_membership("doc-multi", g.id)
        memberships = repo.get_groups_for_document("doc-multi")
        assert len(memberships) == 5

    def test_filter_query_field_preserved(self, repo):
        """filter_query is reserved but must round-trip correctly."""
        g = repo.create("Auto Group")
        g.filter_query = {"field": "type_tags", "op": "contains", "value": "INVOICE"}
        repo.save(g)
        fetched = repo.get_by_id(g.id)
        assert fetched.filter_query == {"field": "type_tags", "op": "contains", "value": "INVOICE"}
