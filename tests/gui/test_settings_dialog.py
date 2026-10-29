import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from gui.settings_dialog import SettingsDialog
from core.config import AppConfig
from core.engines.fluxsense_client import FluxSenseError


@pytest.fixture
def config() -> AppConfig:
    """Test profile with a REST engine configuration (never the user's profile)."""
    cfg = AppConfig(profile="test")
    cfg.set_language("en")
    cfg.set_fluxsense_mode("rest")
    cfg.set_fluxsense_url("http://fluxsense.test:8765")
    cfg.set_fluxsense_timeout(900)
    return cfg


@pytest.mark.localized
def test_settings_dialog_load_save(qtbot, config: AppConfig) -> None:
    """The dialog loads the engine settings and saves changes."""
    dialog = SettingsDialog()
    dialog.config = config
    qtbot.addWidget(dialog)

    assert dialog.combo_lang.currentText() == "en"
    assert dialog.combo_engine_mode.currentData() == "rest"
    assert dialog.edit_engine_url.text() == "http://fluxsense.test:8765"
    assert dialog.spin_engine_timeout.value() == 900

    dialog.combo_lang.setCurrentText("de")
    dialog.combo_engine_mode.setCurrentIndex(dialog.combo_engine_mode.findData("library"))
    dialog.spin_engine_timeout.setValue(1200)

    with qtbot.waitSignal(dialog.settings_changed):
        qtbot.mouseClick(dialog.btn_save, Qt.MouseButton.LeftButton)

    assert config.get_language() == "de"
    assert config.get_fluxsense_mode() == "library"
    assert config.get_fluxsense_timeout() == 1200
    assert config.get_fluxsense_url() == "http://fluxsense.test:8765"


def test_url_row_only_visible_in_rest_mode(qtbot, config: AppConfig) -> None:
    """The service URL is irrelevant for the in-process library."""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    form = dialog.tabs.widget(0).layout()
    dialog.combo_engine_mode.setCurrentIndex(dialog.combo_engine_mode.findData("rest"))
    assert form.isRowVisible(dialog.edit_engine_url)
    dialog.combo_engine_mode.setCurrentIndex(dialog.combo_engine_mode.findData("library"))
    assert not form.isRowVisible(dialog.edit_engine_url)


@pytest.mark.parametrize("health, expected_title", [
    ({"status": "ok", "llm_backend": True, "version": "0.1.0"}, "Success"),
    ({"status": "degraded", "llm_backend": False, "version": "0.1.0"}, "Connection Failed"),
])
def test_engine_connection_test(qtbot, config: AppConfig, health: dict, expected_title: str) -> None:
    """'Test Connection' reports engine and backend state without analyzing anything."""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    client = MagicMock()
    client.health.return_value = health
    with patch("gui.settings_dialog.create_fluxsense_client", return_value=client), \
         patch("gui.settings_dialog.show_selectable_message_box") as box:
        dialog._test_engine_connection()
    assert box.call_args.args[1] == expected_title


def test_engine_connection_test_unavailable(qtbot, config: AppConfig) -> None:
    """An unreachable engine is reported, not raised."""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    client = MagicMock()
    client.health.side_effect = FluxSenseError("unreachable")
    with patch("gui.settings_dialog.create_fluxsense_client", return_value=client), \
         patch("gui.settings_dialog.show_selectable_message_box") as box:
        dialog._test_engine_connection()
    assert box.call_args.args[1] == "Connection Failed"


def test_analyze_signature_saves_profile(qtbot, config: AppConfig) -> None:
    """The identity helper result is stored as the private profile."""
    from core.models.identity import IdentityProfile
    dialog = SettingsDialog()
    dialog.config = MagicMock()
    qtbot.addWidget(dialog)
    dialog.edit_sig_private.setPlainText("Erika Mustermann, Heidestraße 17, 51147 Köln")
    with patch("gui.settings_dialog.parse_identity_signature", return_value=IdentityProfile(name="Erika Mustermann")), \
         patch("gui.settings_dialog.create_fluxsense_client"), \
         patch("gui.settings_dialog.show_selectable_message_box") as box:
        dialog._analyze_signature("PRIVATE")
    assert "Erika Mustermann" in dialog.config.set_private_profile_json.call_args.args[0]
    assert box.call_args.args[1] == "Analysis Successful"
