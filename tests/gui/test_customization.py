import pytest
from PyQt6.QtCore import QSettings, QCoreApplication
import os
from core.database import DatabaseManager
from gui.document_list import DocumentListWidget

@pytest.fixture
def db_manager(tmp_path):
    db_path = tmp_path / "test.db"
    db = DatabaseManager(str(db_path))
    db.init_db()
    return db

def test_column_state_persistence(db_manager, qapp, tmp_path):
    # Setup isolated settings
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    
    QCoreApplication.setOrganizationName("KPaperFluxTest")
    QCoreApplication.setApplicationName("KPaperFluxTest")
    
    # Force use of INI format in a specific directory for isolation
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(settings_dir))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    
    settings = QSettings()
    settings.clear()
    
    widget = DocumentListWidget(db_manager)
    
    # Verify default
    header = widget.tree.header()
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
    header2 = widget2.tree.header()
    
    # Restore happens in __init__
    
    assert header2.isSectionHidden(1)
    assert header2.visualIndex(0) == 2
    
    settings.clear()
