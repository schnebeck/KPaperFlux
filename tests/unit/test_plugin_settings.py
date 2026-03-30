"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_plugin_settings.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Code
Description:    Tests for PluginManager.get_plugin_info_list and the Plugins
                tab in SettingsDialog.
------------------------------------------------------------------------------
"""

import pytest
from unittest.mock import MagicMock, patch

from core.plugins.manager import PluginManager
from core.plugins.base import KPaperFluxPlugin, ApiContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_plugin(info: dict, has_settings: bool = False) -> MagicMock:
    """Return a MagicMock that behaves like a loaded KPaperFluxPlugin."""
    plugin = MagicMock(spec=KPaperFluxPlugin)
    plugin.get_info.return_value = info
    plugin.get_settings_widget.return_value = MagicMock() if has_settings else None
    return plugin


def _make_manager_with_plugins(plugins: list) -> PluginManager:
    """Return a PluginManager whose .plugins list is pre-populated."""
    manager = PluginManager(plugin_dirs=["/fake/plugins"])
    manager.plugins = plugins
    return manager


# ---------------------------------------------------------------------------
# Unit tests for PluginManager.get_plugin_info_list
# ---------------------------------------------------------------------------

def test_get_plugin_info_list_returns_manifest_data():
    """get_plugin_info_list returns correct fields from each plugin's get_info()."""
    plugin_a = _make_mock_plugin(
        {
            "id": "hybrid_assembler",
            "name": "Hybrid PDF Assembler",
            "version": "1.0.0",
            "author": "Antigravity",
            "description": "Combines scanned pages into hybrid PDFs.",
        },
        has_settings=True,
    )
    plugin_b = _make_mock_plugin(
        {
            "id": "order_collection_linker",
            "name": "Order Collection Linker",
            "version": "1.1.0",
            "author": "Antigravity",
            "description": "Automatically links orders to delivery notes.",
        },
        has_settings=False,
    )

    manager = _make_manager_with_plugins([plugin_a, plugin_b])
    result = manager.get_plugin_info_list()

    assert len(result) == 2

    assert result[0]["id"] == "hybrid_assembler"
    assert result[0]["name"] == "Hybrid PDF Assembler"
    assert result[0]["version"] == "1.0.0"
    assert result[0]["author"] == "Antigravity"
    assert result[0]["description"] == "Combines scanned pages into hybrid PDFs."
    assert result[0]["has_settings"] is True

    assert result[1]["id"] == "order_collection_linker"
    assert result[1]["has_settings"] is False


def test_get_plugin_info_list_empty():
    """get_plugin_info_list returns an empty list when no plugins are loaded."""
    manager = _make_manager_with_plugins([])
    assert manager.get_plugin_info_list() == []


def test_get_plugin_info_list_handles_get_info_exception():
    """get_plugin_info_list gracefully handles a plugin whose get_info() raises."""
    plugin = MagicMock(spec=KPaperFluxPlugin)
    plugin.get_info.side_effect = RuntimeError("broken plugin")
    plugin.get_settings_widget.return_value = None

    manager = _make_manager_with_plugins([plugin])
    result = manager.get_plugin_info_list()

    # Should still return one entry with fallback values
    assert len(result) == 1
    assert result[0]["id"] == ""
    assert result[0]["has_settings"] is False


# ---------------------------------------------------------------------------
# GUI tests for SettingsDialog Plugins tab
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_parent(qtbot):
    """A minimal QWidget that satisfies SettingsDialog's parent introspection."""
    from PyQt6.QtWidgets import QWidget
    from unittest.mock import MagicMock
    parent = QWidget()
    parent.app_config = MagicMock()
    parent.app_config.get_language.return_value = "en"
    parent.app_config.get_cached_models.return_value = []
    parent.app_config.get_vault_path.return_value = ""
    parent.app_config.get_ocr_binary.return_value = ""
    parent.app_config.get_transfer_path.return_value = ""
    parent.app_config.get_ai_provider.return_value = "gemini"
    parent.app_config.get_gemini_model.return_value = ""
    parent.app_config.get_api_key.return_value = ""
    parent.app_config.get_ollama_url.return_value = ""
    parent.app_config.get_ollama_model.return_value = ""
    parent.app_config.get_openai_key.return_value = ""
    parent.app_config.get_openai_model.return_value = ""
    parent.app_config.get_anthropic_key.return_value = ""
    parent.app_config.get_anthropic_model.return_value = ""
    parent.app_config.get_ai_retries.return_value = 3
    parent.app_config.get_private_signature.return_value = ""
    parent.app_config.get_business_signature.return_value = ""
    parent.app_config.get_log_level.return_value = "INFO"
    parent.app_config.get_log_components.return_value = {}
    parent.app_config._get_setting.return_value = None
    qtbot.addWidget(parent)
    return parent


def test_settings_dialog_shows_plugin_tab(qtbot, mock_parent):
    """SettingsDialog with a plugin_manager shows a 'Plugins' tab."""
    from gui.settings_dialog import SettingsDialog

    plugin_a = _make_mock_plugin(
        {
            "id": "hybrid_assembler",
            "name": "Hybrid PDF Assembler",
            "version": "1.0.0",
            "author": "Antigravity",
            "description": "Combines scanned pages into hybrid PDFs.",
        }
    )
    manager = _make_manager_with_plugins([plugin_a])

    dialog = SettingsDialog(mock_parent, plugin_manager=manager)
    qtbot.addWidget(dialog)

    tab_texts = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert "Plugins" in tab_texts

    # The table should have one row with the plugin name
    assert dialog.tbl_plugins.rowCount() == 1
    assert dialog.tbl_plugins.item(0, 0).text() == "Hybrid PDF Assembler"


def test_settings_dialog_no_plugin_manager(qtbot, mock_parent):
    """SettingsDialog without a plugin_manager still renders the Plugins tab."""
    from gui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(mock_parent, plugin_manager=None)
    qtbot.addWidget(dialog)

    tab_texts = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert "Plugins" in tab_texts

    # The table should contain the "not available" message
    assert dialog.tbl_plugins.rowCount() == 1
    item_text = dialog.tbl_plugins.item(0, 0).text()
    assert item_text == "Plugin manager not available."


def test_settings_dialog_no_plugins_loaded(qtbot, mock_parent):
    """SettingsDialog with an empty plugin_manager shows 'No plugins loaded.'"""
    from gui.settings_dialog import SettingsDialog

    manager = _make_manager_with_plugins([])
    dialog = SettingsDialog(mock_parent, plugin_manager=manager)
    qtbot.addWidget(dialog)

    assert dialog.tbl_plugins.rowCount() == 1
    item_text = dialog.tbl_plugins.item(0, 0).text()
    assert item_text == "No plugins loaded."
