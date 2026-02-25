
import pytest
from PyQt6.QtCore import Qt
from gui.document_list import DocumentListWidget
from core.database import DatabaseManager
from core.models.virtual import VirtualDocument

@pytest.fixture
def db_manager(tmp_path):
    db_path = str(tmp_path / "test.db")
    db = DatabaseManager(db_path)
    db.init_db()
    return db

def test_clear_filters_resets_archive_mode(qtbot, db_manager):
    """Verify that calling clear_filters resets the is_archive_mode flag."""
    # 1. Setup widget
    widget = DocumentListWidget(db_manager=db_manager)
    qtbot.addWidget(widget)
    
    # 2. Enter Archive mode
    widget.show_archive(True, refresh=False)
    assert widget.is_archive_mode is True
    
    # 3. Simulate breadcrumb "X" click (calls clear_filters)
    widget.clear_filters()
    
    # 4. Verify Archive mode is reset
    assert widget.is_archive_mode is False
    assert widget.is_trash_mode is False
    assert widget.view_context == "All Documents"
