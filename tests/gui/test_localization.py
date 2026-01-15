import os
import sys
import pytest
from pathlib import Path
from PyQt6.QtCore import QTranslator, QLocale, QCoreApplication
from PyQt6.QtWidgets import QApplication

# Ensure core modules can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core.config import AppConfig

@pytest.fixture
def app_config(tmp_path):
    """Fixture to provide a temporary AppConfig."""
    # We mock the HOME directory to avoid messing with real user config
    os.environ["HOME"] = str(tmp_path)
    return AppConfig()

def test_german_translation_loading(app_config, qtbot):
    """
    Test that the German translation file is found and loaded correctly.
    """
    # 1. Setup: Ensure we are testing with 'de' language
    # Assuming config is defaulted or we can force it.
    # For this test, we test the Loading Logic which happens in main.py usually,
    # but here we test the QTranslator mechanism specifically on our generated file.
    
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    translator = QTranslator()
    
    # Locate the generated .qm file
    # It should be in resources/translations/kpaperflux_de.qm
    base_dir = Path(__file__).resolve().parent.parent.parent
    qm_path = base_dir / "resources" / "translations" / "kpaperflux_de.qm"
    
    assert qm_path.exists(), f"Translation file not found at {qm_path}"

    # 2. Action: Load the translator
    loaded = translator.load(str(qm_path))
    assert loaded is True, "Failed to load .qm file into QTranslator"
    
    # 3. Verify: Check a specific translation
    # We assume 'File' -> 'Datei' based on our .ts file
    
    # Note: Using a context that exists in the .ts file
    # Context: MainWindow, Source: File
    translated_text = translator.translate("MainWindow", "File")
    
    # If translation works, it should be 'Datei'
    assert translated_text == "Datei", f"Expected 'Datei', got '{translated_text}'"

def test_app_config_language_setting(app_config):
    """Test that AppConfig can save/retrieve language setting."""
    app_config.set_language("de")
    assert app_config.get_language() == "de"
    
    app_config.set_language("en")
    assert app_config.get_language() == "en"
