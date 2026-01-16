import os
import sys
import pytest
from PyQt6.QtCore import QSettings

# Ensure core modules can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core.config import AppConfig

@pytest.fixture
def clean_config(tmp_path):
    """Fixture to provide a clean AppConfig using a temporary QSettings file."""
    # QSettings with a specific path
    settings_path = str(tmp_path / "test_config.ini")
    settings = QSettings(settings_path, QSettings.Format.IniFormat)
    
    # Patch AppConfig to use this settings object
    config = AppConfig()
    config.settings = settings
    return config

def test_api_key_storage(clean_config):
    """Test setting and getting API key."""
    # 1. Default should be empty (assuming no env var or mocked env var)
    # We mock os.environ
    original_env = os.environ.get("GEMINI_API_KEY")
    if "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]
        
    try:
        assert clean_config.get_api_key() == ""
        
        # 2. Set key
        clean_config.set_api_key("test_key_123")
        assert clean_config.get_api_key() == "test_key_123"
        
        # 3. Persistence
        clean_config.settings.beginGroup("AI")
        val = clean_config.settings.value(AppConfig.KEY_API_KEY)
        clean_config.settings.endGroup()
        assert val == "test_key_123"
        
    finally:
        if original_env:
            os.environ["GEMINI_API_KEY"] = original_env

def test_api_key_fallback(clean_config):
    """Test fallback to environment variable."""
    # Ensure config is empty
    clean_config.set_api_key("")
    
    # Set Env Var
    os.environ["GEMINI_API_KEY"] = "env_key_ABC"
    
    try:
        # Should return env key
        assert clean_config.get_api_key() == "env_key_ABC"
        
        # Explicit config overrides env
        clean_config.set_api_key("config_key_XYZ")
        assert clean_config.get_api_key() == "config_key_XYZ"
        
    finally:
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
