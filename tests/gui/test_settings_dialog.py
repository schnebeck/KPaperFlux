import pytest
from PyQt6.QtCore import Qt
from gui.settings_dialog import SettingsDialog
from core.config import AppConfig

@pytest.mark.localized
def test_settings_dialog_load_save(qtbot):
    """Test that dialog loads config and saves changes."""
    # Setup initial config
    config = AppConfig()
    config.set_language("en")
    config.set_gemini_model("gemini-2.0-flash")
    
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    
    # Check loaded values
    assert dialog.combo_lang.currentText() == "en"
    assert dialog.combo_model.currentText() == "gemini-2.0-flash"
    
    # Modify values
    dialog.combo_lang.setCurrentText("de")
    dialog.combo_model.setCurrentText("gemini-1.5-pro")
    
    # Save
    with qtbot.waitSignal(dialog.settings_changed):
        qtbot.mouseClick(dialog.btn_save, Qt.MouseButton.LeftButton)
        
    # Verify persistence
    assert config.get_language() == "de"
    assert config.get_gemini_model() == "gemini-1.5-pro"
