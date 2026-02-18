import pytest
from unittest.mock import patch
from PyQt6.QtCore import QLocale

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
