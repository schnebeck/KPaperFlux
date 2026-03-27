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

import json
from typing import Any, Dict, List, Optional

from core.logger import get_logger, get_silent_logger
from core.models.semantic import SemanticExtraction
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
        Convert a single database row into a VirtualDocument.

        Args:
            row: A sqlite3.Row, dict, or plain tuple from the DB cursor.

        Returns:
            A hydrated Document, or None if the row is empty or hydration
            fails critically.
        """
        if not row:
            return None

        if hasattr(row, "keys"):
            data: Dict[str, Any] = dict(row)
        elif isinstance(row, dict):
            data = row
        else:
            # Plain tuple fallback — relies on Document.from_row() positional mapping
            return Document.from_row(row)

        type_tags = self._safe_json(data.get("type_tags"), [])
        semantic_raw = self._safe_json(data.get("semantic_data"), {})
        tags = self._parse_tags(data.get("tags"), data.get("uuid"))
        source_mapping = self._safe_json(data.get("source_mapping"), [])
        semantic_data = self._hydrate_semantic(semantic_raw, data.get("uuid"))

        doc_data: Dict[str, Any] = {
            "uuid":             data.get("uuid"),
            "source_mapping":   source_mapping,
            "extra_data":       {},
            "status":           data.get("status"),
            "original_filename": (
                data.get("export_filename")
                or f"Entity {str(data.get('uuid'))[:8]}"
            ),
            "page_count":       data.get("page_count_virt"),
            "created_at":       data.get("created_at"),
            "last_used":        data.get("last_used"),
            "last_processed_at": data.get("last_processed_at"),
            "is_immutable":     bool(data.get("is_immutable", False)),
            "deleted":          bool(data.get("deleted", False)),
            "type_tags":        type_tags,
            "cached_full_text": data.get("cached_full_text"),
            "text_content":     data.get("cached_full_text"),
            "semantic_data":    semantic_data,
            "tags":             tags,
            "deleted_at":       data.get("deleted_at"),
            "locked_at":        data.get("locked_at"),
            "exported_at":      data.get("exported_at"),
            "archived":         bool(data.get("archived", False)),
            "storage_location": data.get("storage_location"),
            "ai_confidence":    float(data.get("ai_confidence", 1.0)),
            "process_id":       data.get("process_id"),
        }

        try:
            return Document(**doc_data)
        except Exception as e:
            logger.error(
                f"CRITICAL: VirtualDocument hydration failed for UUID "
                f"{doc_data.get('uuid')}: {e}"
            )
            logger.debug(f"Faulty doc_data: {doc_data}")
            return None

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _safe_json(raw: Optional[str], default: Any = None) -> Any:
        """Deserialise a JSON string; return *default* on failure or empty input."""
        if not raw:
            return default
        try:
            if isinstance(raw, (bytes, str)):
                return json.loads(raw)
            return raw
        except (json.JSONDecodeError, TypeError) as e:
            get_silent_logger().debug(f"JSON failure in row hydration: {e}")
            return default

    @staticmethod
    def _parse_tags(raw: Any, uuid: Optional[str]) -> List[str]:
        """Parse the tags column (JSON array or comma string) into a list."""
        if not raw:
            return []
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, str):
                return [t.strip() for t in parsed.split(",") if t.strip()]
            return parsed
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Error parsing tags for {uuid}: {e}")
            return []

    @staticmethod
    def _hydrate_semantic(
        raw: Dict[str, Any], uuid: Optional[str]
    ) -> Optional[SemanticExtraction]:
        """Parse semantic_data JSON dict into a SemanticExtraction model."""
        if not raw:
            return None
        try:
            return SemanticExtraction(**raw)
        except Exception as e:
            logger.warning(f"Metadata degradation for {uuid}: {e}")
            return None
