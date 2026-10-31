"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_row_mapping.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    VirtualDocument.from_row is the single column mapping; the
                display hydrator adds only list-view defaults.
------------------------------------------------------------------------------
"""
import json

import pytest

from core.document_hydrator import DocumentHydrator
from core.models.virtual import VirtualDocument

ROW = {
    "uuid": "11111111-2222-4333-8444-555555555555", "source_mapping": '[{"file_uuid": "f", "pages": [1, 2]}]',
    "status": "PROCESSED", "export_filename": "2026-01-01__Sample__INVOICE.pdf", "thumbnail_path": "/thumbs/t.png",
    "pdf_class": "AB", "cached_full_text": "synthetic text", "type_tags": '["INVOICE"]', "tags": '["tax"]',
    "semantic_data": json.dumps({"direction": "INBOUND"}), "page_count_virt": 2, "archived": 1,
    "storage_location": "Box A", "ai_confidence": 0.75, "process_id": "nexus_1",
}


def test_both_paths_map_the_same_columns():
    model = VirtualDocument.from_row(ROW)
    shown = DocumentHydrator().hydrate(ROW)
    for field in ("thumbnail_path", "pdf_class", "export_filename", "status", "tags", "type_tags",
                  "archived", "storage_location", "ai_confidence", "process_id", "page_count"):
        assert getattr(shown, field) == getattr(model, field), field
    assert shown.pdf_class == "AB" and shown.thumbnail_path == "/thumbs/t.png"
    assert shown.semantic_data.direction == "INBOUND"
    assert shown.text_content == "synthetic text"


def test_filename_fallback_is_for_display_only():
    row = {**ROW, "export_filename": None}
    assert VirtualDocument.from_row(row).original_filename is None
    assert DocumentHydrator().hydrate(row).original_filename == "Entity 11111111"


def test_invalid_semantic_data_degrades_only_in_tolerant_mode():
    row = {**ROW, "semantic_data": json.dumps({"ai_confidence": "very high", "workflows": "not a dict"})}
    shown = DocumentHydrator().hydrate(row)
    assert shown is not None and shown.semantic_data is None
    with pytest.raises(ValueError):
        VirtualDocument.from_row(row)


def test_legacy_comma_separated_tags():
    assert VirtualDocument.from_row({**ROW, "tags": "tax, 2025"}).tags == ["tax", "2025"]
