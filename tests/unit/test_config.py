import pytest
from PyQt6.QtCore import QSettings
from core.config import AppConfig

@pytest.fixture
def config():
    # Use a temporary setup for QSettings to avoid polluting real config
    # Creating QSettings with specific scope usually isolates it, or we mock it.
    # Here we rely on the specific org/app name. 
    # Ideally for tests we might want to mock QSettings, but integration test uses real one.
    settings = QSettings("KPaperFlux", "TestConfig")
    settings.clear()
    
    app_config = AppConfig()
    app_config.settings = settings
    return app_config

def test_defaults(config):
    assert "vault" in config.get_vault_path()
    assert config.get_ocr_binary() == "ocrmypdf"
    assert config.get_gemini_model() == "gemini-2.0-flash"
    assert config.get_language() == "en"

def test_set_get_values(config):
    config.set_vault_path("/tmp/test_vault")
    assert config.get_vault_path() == "/tmp/test_vault"
    
    config.set_gemini_model("gemini-1.5-pro")
    assert config.get_gemini_model() == "gemini-1.5-pro"
    
    config.set_language("de")
    assert config.get_language() == "de"
