from PyQt6.QtCore import QSettings
import pytest
import os
from pathlib import Path

from core.config import AppConfig

pytestmark = pytest.mark.localized

@pytest.fixture
def temp_config_file(tmp_path):
    return str(tmp_path / "test_clean.conf")

def test_clean_ini_section_headers(temp_config_file):
    """
    Verify that the config file is written with clean [Section] headers
    instead of encoded [%Section] headers.
    """
    settings = QSettings(temp_config_file, QSettings.Format.IniFormat)
    
    # Manually use the logic that AppConfig uses (or will use)
    # Ideally we test AppConfig directly, but we need to see the file output.
    
    config = AppConfig(profile="test")
    config.settings = settings
    
    # 1. Set values
    config.set_language("de")
    config.set_api_key("secret123")
    config.set_vault_path("/tmp/vault")
    
    # Force sync to disk
    config.settings.sync()
    
    # 2. Read file content
    with open(temp_config_file, "r") as f:
        content = f.read()
        
    print(f"\nConfig Content:\n{content}\n")
    
    # 3. Assertions
    if "[General]" not in content:
        pytest.fail(f"Missing [General] header. Content:\n{content}")
    assert "language=de" in content
    assert "[%General]" not in content, "Should NOT have encoded [%General] header"
    
    # Check other sections
    assert "[AI]" in content
    assert "api_key=secret123" in content
    assert "[Storage]" in content
    
def test_persistence_read_back(temp_config_file):
    """
    Verify that we can read back values correctly from a clean file.
    """
    # Create a clean INI file manually
    with open(temp_config_file, "w") as f:
        f.write("[General]\nlanguage=de\n\n[AI]\napi_key=abc\n")
        
    settings = QSettings(temp_config_file, QSettings.Format.IniFormat)
    config = AppConfig(profile="test")
    config.settings = settings
    
    assert config.get_language() == "de"
    assert config.get_api_key() == "abc"

def test_whitespace_stripping(temp_config_file):
    """
    Verify that setters strip whitespace/newlines to prevent \n in INI files.
    """
    settings = QSettings(temp_config_file, QSettings.Format.IniFormat)
    config = AppConfig(profile="test")
    config.settings = settings
    
    # Set value with newline
    config.set_vault_path("/tmp/vault\n")
    config.set_api_key(" secret_key  ")
    
    # Sync
    config.settings.sync()
    
    # Read back (should be stripped)
    assert config.get_vault_path() == "/tmp/vault"
    assert config.get_api_key() == "secret_key"
    
    # Check file content
    with open(temp_config_file, "r") as f:
        content = f.read()
    
    # Should NOT contain escaped newline
    assert "\\n" not in content
    assert "vault_path=/tmp/vault\n" in content

