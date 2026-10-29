"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_review_markers.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    MetadataEditor per-field review: amber markers with reasons /
                provenance, clearing by edit or confirmation, persisted
                confirmations, the review banner and the FluxSense body tabs.
                Documents come from the synthetic FluxSense fixture through
                the real adapter. No modal dialogs.
------------------------------------------------------------------------------
"""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt

from core.database import DatabaseManager
from core.engines.fluxsense_adapter import adapt_result, flatten_source_mapping
from core.models.virtual import SourceReference, VirtualDocument
from core.repositories import LogicalRepository
from gui.metadata_editor import ROLE_FIELD_PATH, MetadataEditorWidget
from gui.widgets import review_marker

FIXTURE = Path(__file__).parent.parent / "resources" / "fluxsense" / "synthetic_stack_result.json"


@pytest.fixture
def entities() -> list:
    """Invoice, statement and letter of the synthetic stack, adapted like in production."""
    result = json.loads(FIXTURE.read_text(encoding="utf-8"))
    refs = flatten_source_mapping([SourceReference(file_uuid="f", pages=[1, 2, 3, 4, 5])])
    return adapt_result(result, refs)


@pytest.fixture
def db() -> DatabaseManager:
    """In-memory database."""
    manager = DatabaseManager(":memory:")
    manager.init_db()
    return manager


def _stored(db: DatabaseManager, entity: Any, uuid: str) -> VirtualDocument:
    """Saves an adapted entity and reads it back (as the editor gets it)."""
    LogicalRepository(db).save(VirtualDocument(uuid=uuid, source_mapping=entity.source_mapping, type_tags=entity.type_tags,
                                               semantic_data=entity.semantic, status="PROCESSED"))
    return db.get_document_by_uuid(uuid)


@pytest.fixture
def editor(qtbot, db: DatabaseManager) -> MetadataEditorWidget:
    """Editor on the in-memory database."""
    widget = MetadataEditorWidget(db_manager=db)
    qtbot.addWidget(widget)
    return widget


def _semantic_row(editor: MetadataEditorWidget, path: str) -> int:
    """Row of the semantic table that shows a full field path."""
    for row in range(editor.semantic_table.rowCount()):
        if editor.semantic_table.item(row, 1).data(ROLE_FIELD_PATH) == path:
            return row
    raise AssertionError(f"no row for {path}")


def test_flagged_values_are_marked_with_reasons(editor: MetadataEditorWidget, db: DatabaseManager, entities: list) -> None:
    """The invoice flags due_date (model only) and the nulled phone: rows marked, banner counts 2."""
    editor.display_document(_stored(db, entities[0], "inv"))
    assert editor.review_banner.isVisibleTo(editor)
    assert editor.open_review_count() == 2
    assert "2 field(s) need review" in editor.lbl_review_count.text()

    row = _semantic_row(editor, "bodies.finance_body.due_date")
    item = editor.semantic_table.item(row, 2)
    assert item.data(review_marker.ROLE_NEEDS_REVIEW) is True
    assert "model reading only" in item.toolTip()
    assert "Source: read by the AI model only" in item.toolTip()

    phone_tip = editor.semantic_table.item(_semantic_row(editor, "meta_header.sender.phone"), 2).toolTip()
    assert "Originally read: +49 30 7654321" in phone_tip

    accepted = editor.semantic_table.item(_semantic_row(editor, "bodies.finance_body.invoice_number"), 2)
    assert not accepted.data(review_marker.ROLE_NEEDS_REVIEW)


def test_widget_marker_and_inline_confirm(editor: MetadataEditorWidget, db: DatabaseManager, entities: list) -> None:
    """A flagged sender marks the sender field; its inline confirm action clears it."""
    invoice = entities[0]
    invoice.semantic.engine.field_state("meta_header.sender.company").auto_accepted = False
    invoice.semantic.engine.field_state("meta_header.sender.company").review_reasons = ["geometry/model conflict"]
    editor.display_document(_stored(db, invoice, "inv"))

    assert review_marker.is_marked(editor.sender_edit)
    assert "geometry/model conflict" in editor.sender_edit.toolTip()
    assert editor.open_review_count() == 3
    action = editor._confirm_actions[editor.sender_edit]
    action.trigger()
    assert not review_marker.is_marked(editor.sender_edit)
    assert not review_marker.is_marked(editor.pay_recipient_edit)  # same paths
    assert editor.open_review_count() == 2
    assert editor.btn_save.isEnabled()


def test_editing_clears_the_marker(qtbot, editor: MetadataEditorWidget, db: DatabaseManager, entities: list) -> None:
    """Typing into a flagged field confirms it."""
    invoice = entities[0]
    invoice.semantic.engine.field_state("bodies.finance_body.monetary_summation.grand_total_amount").auto_accepted = False
    editor.display_document(_stored(db, invoice, "inv"))
    assert review_marker.is_marked(editor.pay_amount_edit)
    qtbot.keyClicks(editor.pay_amount_edit, "0")
    assert not review_marker.is_marked(editor.pay_amount_edit)


def test_confirmations_are_saved(editor: MetadataEditorWidget, db: DatabaseManager, entities: list) -> None:
    """Confirm all + save stores confirmed_by_user and a timestamp; review_count drops to 0."""
    editor.display_document(_stored(db, entities[0], "inv"))
    editor.confirm_all_review_fields()
    assert not editor.review_banner.isVisibleTo(editor)
    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()
    stored = db.get_document_by_uuid("inv")
    state = stored.semantic_data.engine.field_state("bodies.finance_body.due_date")
    assert state.confirmed_by_user is True and state.confirmed_at
    assert stored.review_count == 0
    raw = db.connection.execute("SELECT json_extract(semantic_data, '$.engine.review_count') FROM virtual_documents "
                                "WHERE uuid = 'inv'").fetchone()[0]
    assert raw == 0

    editor.display_document(stored)
    assert editor.open_review_count() == 0
    assert not review_marker.is_marked(editor.sender_edit)


def test_semantic_table_edit_confirms_the_row(editor: MetadataEditorWidget, db: DatabaseManager, entities: list) -> None:
    """Editing a flagged value in the semantic table clears its marker."""
    editor.display_document(_stored(db, entities[0], "inv"))
    row = _semantic_row(editor, "bodies.finance_body.due_date")
    editor.semantic_table.item(row, 2).setText("2026-03-30")
    assert not editor.semantic_table.item(row, 2).data(review_marker.ROLE_NEEDS_REVIEW)
    assert editor.open_review_count() == 1


def test_statement_tab(editor: MetadataEditorWidget, db: DatabaseManager, entities: list) -> None:
    """Bank statements get a tab with period, balances and the bookings table; edits are saved."""
    editor.display_document(_stored(db, entities[1], "stm"))
    index = editor.tab_widget.indexOf(editor.statement_tab)
    assert editor.tab_widget.isTabVisible(index)
    assert editor.tab_widget.tabText(index) == "Statement"
    assert editor.statement_tab.editors["period_start"].text() == "2026-03-01"
    assert editor.statement_tab.editors["closing_balance"].text() == "943.00"
    assert editor.statement_tab.table.rowCount() == 3
    assert editor.statement_tab.table.item(2, 4).text() == "-357.00"
    assert not editor.tab_widget.isTabVisible(editor.tab_widget.indexOf(editor.payslip_tab))

    editor.statement_tab.editors["closing_balance"].setText("944.00")
    editor.statement_tab.editors["closing_balance"].textEdited.emit("944.00")
    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()
    body = db.get_document_by_uuid("stm").semantic_data.bodies["statement_body"]
    assert float(body.closing_balance) == 944.0
    assert len(body.transactions) == 3


def test_correspondence_tab_and_letter_bodies_survive_save(editor: MetadataEditorWidget, db: DatabaseManager,
                                                           entities: list) -> None:
    """Letters show the correspondence tab; saving keeps correspondence_body."""
    editor.display_document(_stored(db, entities[2], "let"))
    tab = editor.correspondence_tab
    assert editor.tab_widget.isTabVisible(editor.tab_widget.indexOf(tab))
    assert tab.editors["subject"].text() == "Ankündigung Zählerwechsel"
    assert tab.editors["reference_numbers"].text() == "Z-555"
    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()
    assert db.get_document_by_uuid("let").semantic_data.bodies["correspondence_body"]["subject"] == "Ankündigung Zählerwechsel"


def test_save_keeps_bodies_of_fluxsense_types(editor: MetadataEditorWidget, db: DatabaseManager, entities: list) -> None:
    """Regression: a LEGAL_CORRESPONDENCE document kept losing its legal_body on save."""
    letter = entities[2]
    letter.semantic.bodies["legal_body"] = {"contract_id": "V-77"}
    letter.type_tags = ["LEGAL_CORRESPONDENCE", "INBOUND"]
    editor.display_document(_stored(db, letter, "legal"))
    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()
    assert db.get_document_by_uuid("legal").semantic_data.bodies["legal_body"].contract_id == "V-77"


def test_changing_the_type_drops_bodies_of_the_old_type(editor: MetadataEditorWidget, db: DatabaseManager,
                                                        entities: list) -> None:
    """Re-typing a statement as an invoice drops statement_body (FluxSense layout)."""
    editor.display_document(_stored(db, entities[1], "stm"))
    editor.doc_types_combo.setCheckedItems(["INVOICE"])
    with patch("gui.metadata_editor.show_notification"):
        editor.save_changes()
    assert "statement_body" not in db.get_document_by_uuid("stm").semantic_data.bodies


def test_documents_without_engine_data_show_no_markers(editor: MetadataEditorWidget) -> None:
    """Manually created documents have no review state."""
    editor.display_document(VirtualDocument(uuid="manual"))
    assert editor.open_review_count() == 0
    assert not editor.review_banner.isVisibleTo(editor)



def test_save_keeps_string_fields_that_look_numeric(editor: MetadataEditorWidget, db: DatabaseManager, entities: list) -> None:
    """Regression: saving retyped postcodes / house numbers to int and failed validation (nothing semantic was saved)."""
    editor.display_document(_stored(db, entities[0], "inv"))
    row = _semantic_row(editor, "meta_header.doc_number")
    editor.semantic_table.item(row, 2).setText("RE-2026-0043")
    with patch("gui.metadata_editor.show_notification") as notify:
        editor.save_changes()
    assert "could not be re-validated" not in str(notify.call_args_list)
    stored = db.get_document_by_uuid("inv").semantic_data.meta_header
    assert stored.doc_number == "RE-2026-0043"
    assert stored.sender.zip_code == "10115" and stored.recipient.house_number == "17"


def test_typed_value_follows_the_original_type() -> None:
    """Edited values keep the type of the stored value."""
    typed = MetadataEditorWidget._typed_value
    assert typed("01067", "str") == "01067"
    assert typed("12", "int") == 12
    assert typed("12.5", "float") == 12.5
    assert typed("true", "bool") is True
    assert typed("", "str") is None
    assert typed("42", None) == 42
    assert typed("x", "int") == "x"
