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
