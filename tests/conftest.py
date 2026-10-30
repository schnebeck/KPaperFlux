import os
import shutil
import tempfile
from pathlib import Path

import pytest
from unittest.mock import patch
from PyQt6.QtCore import QLocale

_ISOLATED_HOME: Path = Path(tempfile.mkdtemp(prefix="kpaperflux-test-home-"))

@pytest.fixture(autouse=True)
def force_english_locale(request):
    """Ensures most tests run in English locale to avoid label mismatches."""
    # Skip if test is explicitly marked as 'localized' (e.g. testing the l10n system itself)
    if "localized" in request.keywords:
        yield
        return

    # Set Qt's default locale
    original_locale = QLocale.system()
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    
    # Mock AppConfig.get_language to always return 'en'
    with patch("core.config.AppConfig.get_language", return_value="en"):
        yield
    
    # Restore
    QLocale.setDefault(original_locale)

def pytest_configure(config):
    config.addinivalue_line("markers", "localized: mark test to run with real language settings")
    # Redirect HOME and the XDG locations before any QSettings/QStandardPaths lookup,
    # so tests never touch the user's real configuration or data.
    os.environ["HOME"] = str(_ISOLATED_HOME)
    for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                     ("XDG_CACHE_HOME", ".cache")):
        path = _ISOLATED_HOME / sub
        path.mkdir(parents=True, exist_ok=True)
        os.environ[var] = str(path)


def pytest_unconfigure(config):
    shutil.rmtree(_ISOLATED_HOME, ignore_errors=True)

def pytest_addoption(parser):
    parser.addoption(
        "--level2", action="store_true", default=False, help="run level 2 intensive integration tests"
    )

def pytest_collection_modifyitems(config, items):
    if config.getoption("--level2"):
        # --level2 given in cli: do not skip
        return
    skip_level2 = pytest.mark.skip(reason="need --level2 option to run")
    for item in items:
        if "level2" in item.keywords:
            item.add_marker(skip_level2)
