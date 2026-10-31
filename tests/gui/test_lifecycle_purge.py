"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_lifecycle_purge.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    'Delete Permanently' in the trash really purges documents.
------------------------------------------------------------------------------
"""
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QWidget

from core.database import DatabaseManager
from core.models.virtual import SourceReference, VirtualDocument
from core.pipeline import PipelineProcessor
from gui.controllers.lifecycle_controller import LifecycleController


def test_purge_removes_documents_from_the_database(qtbot, tmp_path):
    db = DatabaseManager(str(tmp_path / "purge.db"))
    db.init_db()
    pipeline = PipelineProcessor(vault=MagicMock(), db=db)
    pipeline.physical_cleanup = MagicMock()
    pipeline.logical_repo.save(VirtualDocument(uuid="trashed", deleted=True,
                                               source_mapping=[SourceReference(file_uuid="f", pages=[1])]))
    parent = QWidget()
    qtbot.addWidget(parent)
    controller = LifecycleController(parent, pipeline, db)

    with patch("gui.utils.show_notification"):
        controller.purge_documents(["trashed"])

    assert pipeline.logical_repo.get_by_uuid("trashed") is None
    pipeline.physical_cleanup.assert_called_once_with(["f"])


def test_delete_of_an_active_document_never_purges_even_in_stale_trash_mode(qtbot, tmp_path):
    from PyQt6.QtWidgets import QMessageBox

    db = DatabaseManager(str(tmp_path / "trash.db"))
    db.init_db()
    pipeline = PipelineProcessor(vault=MagicMock(), db=db)
    pipeline.physical_cleanup = MagicMock()
    pipeline.logical_repo.save(VirtualDocument(uuid="active", source_mapping=[SourceReference(file_uuid="f", pages=[1])]))
    parent = QWidget()
    qtbot.addWidget(parent)
    controller = LifecycleController(parent, pipeline, db)
    controller._is_trash_mode = True  # view state left over from the trash view

    with patch("gui.utils.show_selectable_message_box", return_value=QMessageBox.StandardButton.Yes), \
         patch("gui.utils.show_notification"):
        controller.delete_documents(["active"])

    doc = pipeline.logical_repo.get_by_uuid("active")
    assert doc is not None and doc.deleted  # moved to the trash, not purged
    pipeline.physical_cleanup.assert_not_called()
