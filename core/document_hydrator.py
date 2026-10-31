"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/document_hydrator.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Converts raw SQLite row dicts into fully hydrated VirtualDocument
                objects.  Extracted from DatabaseManager to keep the DB layer
                focused on query execution and connection management.
------------------------------------------------------------------------------
"""

from typing import Any, Optional

from core.logger import get_logger
from core.models.virtual import VirtualDocument as Document

logger = get_logger("core.document_hydrator")


class DocumentHydrator:
    """
    Converts a raw database row (sqlite3.Row, dict, or tuple) into a
    fully hydrated VirtualDocument.

    This class is stateless — ``hydrate()`` is a pure transformation.
    It is instantiated once inside DatabaseManager and reused for every
    query result.
    """

    def hydrate(self, row: Any) -> Optional[Document]:
        """
        Convert a single database row into a VirtualDocument for display.

        Builds on VirtualDocument.from_row (the single column mapping) in
        tolerant mode and adds the list view's defaults.

        Args:
            row: A sqlite3.Row or dict from the DB cursor.

        Returns:
            A hydrated Document, or None if the row is empty or hydration fails.
        """
        if not row:
            return None
        try:
            doc = Document.from_row(row, tolerant=True)
        except (ValueError, TypeError, KeyError) as e:
            uuid = dict(row).get("uuid") if hasattr(row, "keys") else None
            logger.error(f"CRITICAL: VirtualDocument hydration failed for UUID {uuid}: {e}")
            return None
        # Display defaults: never persisted (the repository path keeps the raw values)
        if not doc.original_filename:
            doc.original_filename = f"Entity {str(doc.uuid)[:8]}"
        doc.text_content = doc.cached_full_text
        return doc
