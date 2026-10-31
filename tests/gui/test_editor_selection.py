"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_editor_selection.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Editor behaviour when documents are selected through the main
                window: multi-selection saves and unsaved edits.
------------------------------------------------------------------------------
"""
from unittest.mock import patch

import pytest

from core.database import DatabaseManager
from core.models.virtual import VirtualDocument as Document
from gui.main_window import MainWindow


@pytest.fixture
def db(tmp_path) -> DatabaseManager:
    db = DatabaseManager(str(tmp_path / "selection.db"))
    db.init_db()
    db.insert_document(Document(uuid="doc-a", original_filename="a.pdf", tags=["shared"]))
    db.insert_document(Document(uuid="doc-b", original_filename="b.pdf", tags=["shared"]))
    return db


@pytest.fixture
def window(qtbot, db) -> MainWindow:
    mw = MainWindow(pipeline=None, db_manager=db)
    qtbot.addWidget(mw)
    return mw


def test_multi_selection_is_not_dirty(window):
    window._on_document_selected(["doc-a", "doc-b"])

    assert not window.editor_widget.btn_save.isEnabled()


def test_multi_selection_save_keeps_each_filename(window, db):
    window._on_document_selected(["doc-a", "doc-b"])
    window.editor_widget.tags_edit.setTags(["shared", "batch"])

    with patch("gui.metadata_editor.show_notification"):
        window.editor_widget.save_changes()

    assert db.get_document_by_uuid("doc-a").original_filename == "a.pdf"
    assert db.get_document_by_uuid("doc-b").original_filename == "b.pdf"
    assert db.get_document_by_uuid("doc-b").tags == ["shared", "batch"]


def _select(window, qtbot, uuids):
    window._on_document_selected(uuids)
    qtbot.wait(50)  # let deferred signals settle


def test_loaded_document_is_not_dirty(window, qtbot):
    _select(window, qtbot, ["doc-a"])

    assert not window.editor_widget.is_dirty()


def test_refresh_of_same_selection_keeps_unsaved_edits(window, qtbot):
    _select(window, qtbot, ["doc-a"])
    window.editor_widget.storage_location_edit.setText("Shelf 3")
    assert window.editor_widget.is_dirty()

    # A background pipeline burst reloads the current selection
    _select(window, qtbot, ["doc-a"])

    assert window.editor_widget.storage_location_edit.text() == "Shelf 3"
    assert window.editor_widget.is_dirty()


@pytest.mark.parametrize("answer, expected", [("Save", "Shelf 3"), ("Discard", None)])
def test_switching_documents_offers_to_save(window, db, qtbot, answer, expected):
    from PyQt6.QtWidgets import QMessageBox

    _select(window, qtbot, ["doc-a"])
    window.editor_widget.storage_location_edit.setText("Shelf 3")

    button = getattr(QMessageBox.StandardButton, answer)
    with patch("gui.metadata_editor.QMessageBox.question", return_value=button) as question, \
         patch("gui.metadata_editor.show_notification"):
        _select(window, qtbot, ["doc-b"])

    question.assert_called_once()
    assert (db.get_document_by_uuid("doc-a").storage_location or None) == expected
    assert window.editor_widget.current_uuids == ["doc-b"]
    assert not window.editor_widget.is_dirty()


def test_german_ui_translates_standard_buttons(window):
    from PyQt6.QtWidgets import QMessageBox

    window._switch_language("de", refresh_ui=False)
    try:
        box = QMessageBox()
        box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard)
        texts = {box.button(b).text().replace("&", "") for b in (QMessageBox.StandardButton.Save,
                                                                  QMessageBox.StandardButton.Discard)}
        assert texts == {"Speichern", "Verwerfen"}
    finally:
        window._switch_language("en", refresh_ui=False)
