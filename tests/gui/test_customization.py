
import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtTest import QTest
from core.database import DatabaseManager
from gui.document_list import DocumentListWidget

@pytest.fixture
def db_manager(tmp_path):
    db_path = tmp_path / "test.db"
    return DatabaseManager(str(db_path))

def test_column_state_persistence(db_manager, qapp):
    # Setup
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(db_manager.db_path)) # Mock settings path? No, QSettings usually uses system.
    # To mock QSettings, we can use a custom logic or just rely on the fact it writes to memory/organization.
    # For CI/Test, we can clear settings first.
    
    settings = QSettings("KPaperFlux", "DocumentList")
    settings.clear()
    
    widget = DocumentListWidget(db_manager)
    
    # Verify default
    header = widget.horizontalHeader()
    # Sections are 0,1,2,3...
    
    # Hide column 1
    widget.toggle_column(1, False)
    assert header.isSectionHidden(1)
    
    # Move column 0 to index 2
    header.moveSection(0, 2)
    # visual index of logical index 0 should be 2
    assert header.visualIndex(0) == 2
    
    # Save
    widget.save_state()
    
    # New Widget
    widget2 = DocumentListWidget(db_manager)
    header2 = widget2.horizontalHeader()
    
    # Restore happens in __init__
    
    assert header2.isSectionHidden(1)
    assert header2.visualIndex(0) == 2
    
    settings.clear()
