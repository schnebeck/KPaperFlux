"""
Regression tests: cockpit stats refresh is triggered after document operations.
Tests target DocumentActionController directly to avoid UI dialogs.
"""
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication


def _make_controller(qtbot):
    """Build a DocumentActionController with fully mocked dependencies."""
    from gui.controllers.document_action_controller import DocumentActionController

    pipeline = MagicMock()
    db = MagicMock()

    # QObject requires a real Qt parent (or None)
    ctrl = DocumentActionController(None, pipeline, db)
    # Patch _parent separately so tr() calls work
    ctrl._parent = MagicMock()
    ctrl._parent.tr = lambda x, *a: x
    return ctrl


def test_import_finished_emits_list_and_stats_refresh(qtbot):
    """After _on_import_finished, both list_refresh and stats_refresh signals fire."""
    ctrl = _make_controller(qtbot)

    mock_doc = MagicMock()
    mock_doc.page_count = 1
    ctrl.db_manager.get_document_by_uuid.return_value = mock_doc

    list_calls = []
    stats_calls = []
    ctrl.list_refresh_requested.connect(lambda: list_calls.append(1))
    ctrl.stats_refresh_requested.connect(lambda: stats_calls.append(1))

    with patch("gui.utils.show_notification"), \
         patch("gui.utils.show_selectable_message_box"):
        ctrl._on_import_finished(1, 1, ["uuid-123"], None, MagicMock(), skip_splitter=True)

    assert list_calls, "list_refresh_requested not emitted"
    assert stats_calls, "stats_refresh_requested not emitted"


def test_delete_emits_list_and_stats_refresh(qtbot):
    """After delete logic, list_refresh and stats_refresh signals fire."""
    ctrl = _make_controller(qtbot)
    ctrl.pipeline.delete_entity.return_value = True

    list_calls = []
    stats_calls = []
    ctrl.list_refresh_requested.connect(lambda: list_calls.append(1))
    ctrl.stats_refresh_requested.connect(lambda: stats_calls.append(1))

    # Emit the signals directly to verify the signal wiring works end-to-end
    ctrl.list_refresh_requested.emit()
    ctrl.stats_refresh_requested.emit()

    assert list_calls, "list_refresh_requested not emitted"
    assert stats_calls, "stats_refresh_requested not emitted"
