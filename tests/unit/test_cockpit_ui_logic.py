"""
Verify that DocumentActionController emits the correct signals after import.
Tests call _on_import_finished directly to avoid dialog interactions.
"""
import unittest
from unittest.mock import MagicMock, patch


class TestCockpitRefresh(unittest.TestCase):

    def test_import_refresh_signals_emitted(self):
        """
        _on_import_finished must emit list_refresh_requested and stats_refresh_requested.
        """
        from gui.controllers.document_action_controller import DocumentActionController

        db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_doc.original_filename = "test.pdf"
        db.get_document_by_uuid.return_value = mock_doc

        # QObject requires None or a real Qt parent — no MagicMock here
        ctrl = DocumentActionController(None, MagicMock(), db)
        ctrl._parent = MagicMock()
        ctrl._parent.tr = lambda x, *a: x

        list_calls = []
        stats_calls = []
        ctrl.list_refresh_requested.connect(lambda: list_calls.append(1))
        ctrl.stats_refresh_requested.connect(lambda: stats_calls.append(1))

        with patch("gui.utils.show_notification"), \
             patch("gui.utils.show_selectable_message_box"):
            ctrl._on_import_finished(1, 1, ["uuid-1"], None, MagicMock(), skip_splitter=True)

        self.assertTrue(list_calls, "list_refresh_requested not emitted")
        self.assertTrue(stats_calls, "stats_refresh_requested not emitted")


if __name__ == "__main__":
    unittest.main()
