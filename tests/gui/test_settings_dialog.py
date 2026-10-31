"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_settings_dialog.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Tests: settings dialog.
------------------------------------------------------------------------------
"""

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
    assert not form.isRowVisible(dialog.edit_engine_llm_url)
    dialog.combo_engine_mode.setCurrentIndex(dialog.combo_engine_mode.findData("library"))
    assert not form.isRowVisible(dialog.edit_engine_url)
    assert form.isRowVisible(dialog.edit_engine_llm_url)


def _wait_for_result(qtbot, dialog, box, calls: int = 1) -> None:
    """The connection test and signature analysis run in a worker thread."""
    qtbot.waitUntil(lambda: box.call_count >= calls, timeout=3000)
    qtbot.waitUntil(lambda: not dialog._busy_worker.isRunning(), timeout=3000)


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
        _wait_for_result(qtbot, dialog, box)
    assert box.call_args.args[1] == expected_title


def test_engine_connection_test_unavailable(qtbot, config: AppConfig) -> None:
    """An unreachable engine is reported, not raised."""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    client = MagicMock()
    client.health.side_effect = FluxSenseError("not installed")
    with patch("gui.settings_dialog.create_fluxsense_client", return_value=client), \
         patch("gui.settings_dialog.show_selectable_message_box") as box:
        dialog._test_engine_connection()
        _wait_for_result(qtbot, dialog, box)
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
        _wait_for_result(qtbot, dialog, box)
    assert "Erika Mustermann" in dialog.config.set_private_profile_json.call_args.args[0]
    assert box.call_args.args[1] == "Analysis Successful"



def test_ai_server_url_defaults_to_fluxsense_config(qtbot, config: AppConfig) -> None:
    """Empty AI server URL by default (FluxSense's config applies); an explicit value is saved."""
    config.set_fluxsense_llm_url("")
    dialog = SettingsDialog()
    dialog.config = config
    qtbot.addWidget(dialog)
    assert dialog.edit_engine_llm_url.text() == ""
    assert dialog.edit_engine_llm_url.placeholderText() == "Empty: use the FluxSense configuration"
    dialog.edit_engine_llm_url.setText(" http://my-ai:8080/v1 ")
    with qtbot.waitSignal(dialog.settings_changed):
        qtbot.mouseClick(dialog.btn_save, Qt.MouseButton.LeftButton)
    assert config.get_fluxsense_llm_url() == "http://my-ai:8080/v1"
    config.set_fluxsense_llm_url("")


def test_unreachable_messages_are_generic(qtbot, config: AppConfig) -> None:
    """Unreachable AI server: address + hint to check the settings, no wake/WOL wording."""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    client = MagicMock()
    client.server_url.return_value = "http://my-ai:8080/v1"
    client.health.return_value = {"status": "degraded", "llm_backend": False, "version": "0.1.0", "server_url": "http://my-ai:8080/v1"}
    with patch("gui.settings_dialog.create_fluxsense_client", return_value=client), \
         patch("gui.settings_dialog.show_selectable_message_box") as box:
        dialog._test_engine_connection()
        _wait_for_result(qtbot, dialog, box)
        degraded = box.call_args.args[2]
        client.health.side_effect = FluxSenseError("refused", "BACKEND_UNREACHABLE")
        dialog._test_engine_connection()
        _wait_for_result(qtbot, dialog, box, calls=2)
        refused = box.call_args.args[2]
    expected = "AI server not reachable at http://my-ai:8080/v1. Please check the AI server settings."
    assert degraded == expected and refused == expected
    assert "wake" not in expected.lower() and "wol" not in expected.lower()



def test_energy_management_is_collapsed_and_off_by_default(qtbot, config: AppConfig) -> None:
    """The optional WOL section starts collapsed and empty; values are saved and passed through as hooks."""
    config.set_fluxsense_wol("", "", "")
    config.set_fluxsense_mode("library")
    dialog = SettingsDialog()
    dialog.config = config
    qtbot.addWidget(dialog)
    dialog.combo_engine_mode.setCurrentIndex(dialog.combo_engine_mode.findData("library"))
    form = dialog.tabs.widget(0).layout()
    assert form.isRowVisible(dialog.btn_engine_advanced)
    assert not dialog.btn_engine_advanced.isChecked() and not form.isRowVisible(dialog.box_energy)
    assert (dialog.edit_wol_url.text(), dialog.edit_wol_device.text(), dialog.edit_wol_token.text()) == ("", "", "")
    assert dialog._energy_hooks() == {}
    assert "sleeps when idle" in dialog.lbl_energy_note.text()

    dialog.btn_engine_advanced.setChecked(True)
    assert form.isRowVisible(dialog.box_energy)
    dialog.edit_wol_url.setText("https://wol.example.test")
    dialog.edit_wol_device.setText("ai-server")
    dialog.edit_wol_token.setText("secret-tool lookup service wol-server")
    assert dialog._energy_hooks() == {"wol_url": "https://wol.example.test", "wol_device": "ai-server",
                                      "wol_token_command": "secret-tool lookup service wol-server"}
    with qtbot.waitSignal(dialog.settings_changed):
        qtbot.mouseClick(dialog.btn_save, Qt.MouseButton.LeftButton)
    assert config.get_fluxsense_hooks()["wol_token_command"] == "secret-tool lookup service wol-server"
    config.set_fluxsense_wol("", "", "")


def test_energy_section_hidden_in_rest_mode(qtbot, config: AppConfig) -> None:
    """The FluxSense service has its own configuration in REST mode."""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.combo_engine_mode.setCurrentIndex(dialog.combo_engine_mode.findData("rest"))
    assert not dialog.tabs.widget(0).layout().isRowVisible(dialog.btn_engine_advanced)


def test_wake_hint_only_with_energy_management(qtbot, config: AppConfig) -> None:
    """Unreachable messages mention waking only when a WOL-Server is configured."""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.edit_wol_url.setText("")
    assert "waking" not in dialog._failure_text("BACKEND_UNREACHABLE", "http://ai:8080/v1")
    dialog.edit_wol_url.setText("https://wol.example.test")
    assert "waking up" in dialog._failure_text("BACKEND_UNREACHABLE", "http://ai:8080/v1")
    assert "did not answer in time" in dialog._failure_text("BACKEND_TIMEOUT", "http://ai:8080/v1")
def test_parallel_analyses_setting(qtbot, config: AppConfig) -> None:
    """The concurrency setting loads (default 2), saves and is clamped by the config."""
    dialog = SettingsDialog()
    dialog.config = config
    qtbot.addWidget(dialog)
    assert dialog.spin_engine_parallel.value() == AppConfig.DEFAULT_ANALYSIS_CONCURRENCY == 2
    assert dialog.spin_engine_parallel.maximum() == AppConfig.MAX_ANALYSIS_CONCURRENCY
    dialog.spin_engine_parallel.setValue(3)
    with qtbot.waitSignal(dialog.settings_changed):
        qtbot.mouseClick(dialog.btn_save, Qt.MouseButton.LeftButton)
    assert config.get_analysis_concurrency() == 3
    config.settings.setValue("AI/analysis_concurrency", 99)
    assert config.get_analysis_concurrency() == AppConfig.MAX_ANALYSIS_CONCURRENCY
    with pytest.raises(ValueError):
        config.set_analysis_concurrency(0)
    config.set_analysis_concurrency(2)


def test_connection_test_keeps_the_dialog_responsive(qtbot, config: AppConfig) -> None:
    """The AI server call runs off the GUI thread: the call returns at once."""
    import threading
    release = threading.Event()
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    client = MagicMock()
    client.health.side_effect = lambda: (release.wait(2), {"status": "ok", "llm_backend": True, "version": "1"})[1]
    with patch("gui.settings_dialog.create_fluxsense_client", return_value=client), \
         patch("gui.settings_dialog.show_selectable_message_box") as box:
        dialog._test_engine_connection()
        assert box.call_count == 0 and dialog._busy_worker.isRunning()
        release.set()
        _wait_for_result(qtbot, dialog, box)
    assert box.call_args.args[1] == "Success"
