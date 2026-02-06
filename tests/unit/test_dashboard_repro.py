import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QMessageBox, QDialog
from gui.main_window import MainWindow

def test_import_refresh_dashboard_called(qtbot):
    """
    Reproduce: Dashboard refresh must be called after import.
    """
    # 1. Setup
    with patch('gui.main_window.MainLoopWorker'), \
         patch('gui.main_window.show_selectable_message_box'):
        mw = MainWindow(db_manager=MagicMock(), pipeline=MagicMock())
        qtbot.addWidget(mw)
        mw.dashboard_widget = MagicMock()
        mw.filter_tree_widget = MagicMock()
        mw.list_widget = MagicMock()
        
        # Prevent pickling errors in QSettings during teardown
        mw.main_loop_worker.is_paused = False
        mw.list_widget.get_selected_uuids.return_value = []
        # 2. Simulate Import Finished
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mw.db_manager.get_document_by_uuid.return_value = mock_doc

        # _on_import_finished(self, success_count, total, imported_uuids, error_msg, progress_dialog)
        mw._on_import_finished(1, 1, ["uuid-123"], None, MagicMock())
        
        # 3. Assertions
        assert mw.dashboard_widget.refresh_stats.called
        assert mw.filter_tree_widget.load_tree.called

def test_delete_refresh_dashboard_called(qtbot):
    """
    Reproduce: Dashboard refresh must be called after delete.
    """
    # 1. Setup
    with patch('gui.main_window.MainLoopWorker'), \
         patch('gui.main_window.show_selectable_message_box') as mock_msgbox:
        mw = MainWindow(db_manager=MagicMock(), pipeline=MagicMock())
        qtbot.addWidget(mw)
        mw.dashboard_widget = MagicMock()
        mw.list_widget = MagicMock()
        
        # Prevent pickling errors in QSettings during teardown
        mw.main_loop_worker.is_paused = False
        mw.list_widget.get_selected_uuids.return_value = ["uuid-to-delete"]
        # Mock Delete Confirmation
        mock_msgbox.return_value = QMessageBox.StandardButton.Yes
        # Mock DB delete
        mw.db_manager.delete_document.return_value = True
        mw.list_widget.get_selected_uuids.return_value = ["uuid-to-delete"]
        
        # 2. Simulate Delete Slot being called
        mw.delete_document_slot(["uuid-to-delete"])
        
        # 3. Assertions
        assert mw.dashboard_widget.refresh_stats.called
