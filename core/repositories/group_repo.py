"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/repositories/group_repo.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Repository for DocumentGroup CRUD and document-group
                membership management. Operates on document_groups and
                document_group_memberships tables.
------------------------------------------------------------------------------
"""
import json
import uuid as _uuid_mod
from typing import List, Optional

from core.models.group import DocumentGroup
from core.repositories.base import BaseRepository
from core.logger import get_logger

logger = get_logger("repositories.group")


class GroupRepository(BaseRepository):
    """Manages document_groups and document_group_memberships tables."""

    # ------------------------------------------------------------------
    # Group CRUD
    # ------------------------------------------------------------------

    def save(self, group: DocumentGroup) -> bool:
        """Insert or replace a group record. Returns True on success."""
        sql = """
        INSERT OR REPLACE INTO document_groups
            (id, name, parent_id, color, icon, description, sort_order, filter_query)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self.db._write() as conn:
                conn.execute(sql, (
                    group.id,
                    group.name,
                    group.parent_id,
                    group.color,
                    group.icon,
                    group.description,
                    group.sort_order,
                    json.dumps(group.filter_query) if group.filter_query else None,
                ))
            return True
        except Exception as exc:
            logger.error(f"GroupRepository.save failed: {exc}")
            return False

    def create(self, name: str, parent_id: Optional[str] = None,
               color: Optional[str] = None, icon: Optional[str] = None) -> Optional[DocumentGroup]:
        """Create a new group with a generated UUID. Returns the new group or None."""
        group = DocumentGroup(
            id=str(_uuid_mod.uuid4()),
            name=name,
            parent_id=parent_id,
            color=color,
            icon=icon or "📁",
        )
        return group if self.save(group) else None

    def get_by_id(self, group_id: str) -> Optional[DocumentGroup]:
        """Return a single group by primary key."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM document_groups WHERE id = ?", (group_id,))
            row = cursor.fetchone()
            return self._row_to_group(row) if row else None
        except Exception as exc:
            logger.error(f"GroupRepository.get_by_id failed: {exc}")
            return None

    def get_all(self) -> List[DocumentGroup]:
        """Return all groups ordered by sort_order, then name."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM document_groups ORDER BY sort_order, name")
            return [self._row_to_group(r) for r in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"GroupRepository.get_all failed: {exc}")
            return []

    def get_children(self, parent_id: Optional[str]) -> List[DocumentGroup]:
        """Return direct children of the given parent (None = top-level groups)."""
        try:
            cursor = self.conn.cursor()
            if parent_id is None:
                cursor.execute(
                    "SELECT * FROM document_groups WHERE parent_id IS NULL ORDER BY sort_order, name"
                )
            else:
                cursor.execute(
                    "SELECT * FROM document_groups WHERE parent_id = ? ORDER BY sort_order, name",
                    (parent_id,),
                )
            return [self._row_to_group(r) for r in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"GroupRepository.get_children failed: {exc}")
            return []

    def rename(self, group_id: str, new_name: str) -> bool:
        """Rename an existing group. Returns True on success."""
        try:
            with self.db._write() as conn:
                conn.execute(
                    "UPDATE document_groups SET name = ? WHERE id = ?",
                    (new_name, group_id),
                )
            return True
        except Exception as exc:
            logger.error(f"GroupRepository.rename failed: {exc}")
            return False

    def delete(self, group_id: str) -> bool:
        """
        Delete a group. Memberships cascade automatically (ON DELETE CASCADE).
        Child groups are re-parented to NULL (ON DELETE SET NULL).
        """
        try:
            with self.db._write() as conn:
                conn.execute("DELETE FROM document_groups WHERE id = ?", (group_id,))
            return True
        except Exception as exc:
            logger.error(f"GroupRepository.delete failed: {exc}")
            return False

    def get_document_count(self, group_id: str) -> int:
        """Return the number of documents currently in the given group."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM document_group_memberships WHERE group_id = ?",
                (group_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception as exc:
            logger.error(f"GroupRepository.get_document_count failed: {exc}")
            return 0

    # ------------------------------------------------------------------
    # Membership
    # ------------------------------------------------------------------

    def add_membership(self, document_uuid: str, group_id: str) -> bool:
        """Add a document to a group. No-op if already a member."""
        try:
            with self.db._write() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO document_group_memberships (document_uuid, group_id) VALUES (?, ?)",
                    (document_uuid, group_id),
                )
            return True
        except Exception as exc:
            logger.error(f"GroupRepository.add_membership failed: {exc}")
            return False

    def remove_membership(self, document_uuid: str, group_id: str) -> bool:
        """Remove a document from a group."""
        try:
            with self.db._write() as conn:
                conn.execute(
                    "DELETE FROM document_group_memberships WHERE document_uuid = ? AND group_id = ?",
                    (document_uuid, group_id),
                )
            return True
        except Exception as exc:
            logger.error(f"GroupRepository.remove_membership failed: {exc}")
            return False

    def get_groups_for_document(self, document_uuid: str) -> List[DocumentGroup]:
        """Return all groups the given document belongs to."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT g.* FROM document_groups g
                JOIN document_group_memberships m ON g.id = m.group_id
                WHERE m.document_uuid = ?
                ORDER BY g.sort_order, g.name
                """,
                (document_uuid,),
            )
            return [self._row_to_group(r) for r in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"GroupRepository.get_groups_for_document failed: {exc}")
            return []

    def get_document_uuids_in_group(self, group_id: str) -> List[str]:
        """Return UUIDs of all documents in the given group."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT document_uuid FROM document_group_memberships WHERE group_id = ?",
                (group_id,),
            )
            return [r[0] for r in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"GroupRepository.get_document_uuids_in_group failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_group(row) -> DocumentGroup:
        d = dict(row) if hasattr(row, "keys") else {
            "id": row[0], "name": row[1], "parent_id": row[2],
            "color": row[3], "icon": row[4], "description": row[5],
            "sort_order": row[6], "filter_query": row[7],
        }
        raw_fq = d.get("filter_query")
        d["filter_query"] = json.loads(raw_fq) if raw_fq else None
        return DocumentGroup(**d)
