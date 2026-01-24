
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QMessageBox
import sys

# Create execution instance if needed
app = QApplication.instance() or QApplication(sys.argv)

from gui.main_window import MainWindow

class TestDashboardRefreshRepro(unittest.TestCase):
    
    @patch('gui.workers.ImportWorker')
    @patch('gui.main_window.AIWorker') 
    @patch('gui.main_window.TagManager') 
    @patch('PyQt6.QtWidgets.QProgressDialog')
    @patch('PyQt6.QtWidgets.QMessageBox')
    def test_import_refresh_dashboard_called(self, mock_msgbox, mock_progress, MockTagManager, MockAIWorker, MockWorker):
        """
        Reproduce: Dashboard refresh must be called after import.
        """
        # 1. Setup
        mw = MainWindow(db_manager=MagicMock(), pipeline=MagicMock())
        mw.dashboard_widget = MagicMock()
        mw.filter_tree_widget = MagicMock()
        mw.ai_worker = MagicMock()
        
        # 2. Simulate Import Finished
        # Configure Mock DB to return a doc with page_count=1 to avoid splitter logic/type errors
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mw.db_manager.get_document_by_uuid.return_value = mock_doc

        # _on_import_finished(self, success_count, total, imported_uuids, error_msg, progress_dialog)
        mw._on_import_finished(1, 1, ["uuid-123"], None, MagicMock())
        
        # 3. Assertions
        # Dashboard refresh check
        if not mw.dashboard_widget.refresh_stats.called:
             self.fail("Dashboard refresh_stats() was NOT called after import!")
             
        # Filter Tree refresh check
        if not mw.filter_tree_widget.load_tree.called:
             self.fail("Filter Tree load_tree() was NOT called after import!")
             
    @patch('PyQt6.QtWidgets.QMessageBox')
    def test_delete_refresh_dashboard_called(self, mock_msgbox):
        """
        Reproduce: Dashboard refresh must be called after delete.
        """
        # 1. Setup
        mw = MainWindow(db_manager=MagicMock(), pipeline=MagicMock())
        mw.dashboard_widget = MagicMock()
        mw.list_widget = MagicMock()
        
        # Mock Delete Confirmation (static method usually)
        mock_msgbox.question.return_value = QMessageBox.StandardButton.Yes
        # Mock DB delete
        mw.db_manager.delete_document.return_value = True
        mw.list_widget.get_selected_uuids.return_value = ["uuid-to-delete"]
        
        # 2. Simulate Delete Slot being called
        # Note: delete_documents_slot may take arguments or use list selection
        mw.delete_documents_slot(["uuid-to-delete"])
        
        # 3. Assertions
        if not mw.dashboard_widget.refresh_stats.called:
             self.fail("Dashboard refresh_stats() was NOT called after delete!")

if __name__ == '__main__':
    unittest.main()
