
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import pyqtSignal, QObject

class MockImportWorker(QObject):
    finished = pyqtSignal(bool, int, list, str)
    progress = pyqtSignal(int, str)
    
    def start(self):
        pass

class TestDashboardRefresh(unittest.TestCase):
    
    @patch('gui.main_window.QProgressDialog')
    @patch('gui.main_window.show_notification')
    def test_import_refresh_dashboard(self, mock_notify, mock_progress_dialog):
        """
        Verify that _on_import_finished calls dashboard_widget.refresh_stats()
        """
        # We don't import MainWindow at top level to avoid circular issues during test patching
        from gui.main_window import MainWindow
        
        # Create mw without calling __init__ to avoid GUI setup
        mw = MagicMock(spec=MainWindow)
        mw.db_manager = MagicMock()
        
        # Mock document returned by DB
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_doc.original_filename = "test.pdf"
        mw.db_manager.get_document_by_uuid.return_value = mock_doc

        mw.dashboard_widget = MagicMock()

        mw.list_widget = MagicMock()
        mw.pipeline = MagicMock()
        mw.tr = lambda x: x
        
        # Real method call
        MainWindow._on_import_finished(mw, 1, 1, ["uuid-1"], None, MagicMock())
        
        # Verify stats refresh
        mw.dashboard_widget.refresh_stats.assert_called_once()
        mw.list_widget.refresh_list.assert_called_once()

if __name__ == '__main__':
    unittest.main()
