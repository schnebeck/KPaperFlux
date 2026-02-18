import os
import sys
import pytest
from pathlib import Path
from PyQt6.QtCore import QTranslator, QLocale, QCoreApplication
from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.localized

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
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    translator = QTranslator()
    
    base_dir = Path(__file__).resolve().parent.parent.parent
    qm_path = base_dir / "resources" / "l10n" / "de" / "gui_strings.qm"
    
    assert qm_path.exists(), f"GUI Translation file not found at {qm_path}. Did you run lrelease?"

    loaded = translator.load(str(qm_path))
    assert loaded is True, "Failed to load .qm file into QTranslator"
    
    # Verify: Check a specific translation
    translated_text = translator.translate("MainWindow", "&File")
    assert translated_text == "&Datei", f"Expected '&Datei', got '{translated_text}'"

def test_translation_coverage():
    """
    Verify that the German translation has reasonable coverage (not too many unfinished).
    """
    import xml.etree.ElementTree as ET
    base_dir = Path(__file__).resolve().parent.parent.parent
    ts_path = base_dir / "resources" / "l10n" / "de" / "gui_strings.ts"
    
    assert ts_path.exists()
    
    tree = ET.parse(ts_path)
    root = tree.getroot()
    
    messages = root.findall(".//message")
    total = len(messages)
    
    unfinished = 0
    for msg in messages:
        trans = msg.find("translation")
        if trans is not None and trans.get("type") == "unfinished":
            unfinished += 1
            
    coverage = (total - unfinished) / total if total > 0 else 0
    
    print(f"[L10N] Total: {total}, Unfinished: {unfinished}, Coverage: {coverage:.1%}")
    
    # We expect at least significant coverage. For dev state, we set 1% as baseline.
    assert coverage >= 0.01, f"Translation coverage too low: {coverage:.1%} ({unfinished}/{total} unfinished)"

def test_app_config_language_setting(app_config):
    """Test that AppConfig can save/retrieve language setting."""
    app_config.set_language("de")
    assert app_config.get_language() == "de"
    
    app_config.set_language("en")
    assert app_config.get_language() == "en"
