"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_user_definition_dirs.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Workflow rules and report definitions live in the user's config
                directory, seeded once from the bundled files in resources/.
------------------------------------------------------------------------------
"""
from pathlib import Path

import pytest

from core.config import AppConfig

DIRS = [("workflows", "get_workflows_dir"), ("reports", "get_reports_dir")]


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    cfg = AppConfig(profile="test-user-dirs")
    monkeypatch.setattr(AppConfig, "get_config_dir", lambda self: tmp_path)
    return cfg


@pytest.mark.parametrize("name, getter", DIRS)
def test_dir_is_inside_config_dir(config: AppConfig, tmp_path: Path, name: str, getter: str) -> None:
    assert getattr(config, getter)() == tmp_path / name


@pytest.mark.parametrize("name, getter", DIRS)
def test_dir_is_seeded_from_bundled_files(config: AppConfig, name: str, getter: str) -> None:
    bundled = sorted(p.name for p in (AppConfig.BUNDLED_RESOURCES_DIR / name).glob("*.json"))
    assert bundled, f"expected bundled {name}"
    seeded = sorted(p.name for p in getattr(config, getter)().glob("*.json"))
    assert seeded == bundled


@pytest.mark.parametrize("name, getter", DIRS)
def test_user_changes_are_not_overwritten_by_reseeding(config: AppConfig, name: str, getter: str) -> None:
    user_dir = getattr(config, getter)()
    files = sorted(user_dir.glob("*.json"))
    files[0].unlink()
    files[1].write_text('{"id": "edited"}', encoding="utf-8")

    getattr(config, getter)()

    assert not files[0].exists()
    assert files[1].read_text(encoding="utf-8") == '{"id": "edited"}'


def test_workflow_manager_uses_user_dir(config: AppConfig, qtbot) -> None:
    from gui.workflow_manager import WorkflowManagerWidget, WorkflowRuleManagerDialog

    widget = WorkflowManagerWidget()
    qtbot.addWidget(widget)
    dialog = WorkflowRuleManagerDialog()
    qtbot.addWidget(dialog)

    expected = str(config.get_workflows_dir())
    assert widget.workflow_dir == expected
    assert dialog.workflow_dir == expected


def test_report_editor_saves_to_user_dir(config: AppConfig, qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    from PyQt6.QtWidgets import QMessageBox
    from gui.report_editor import ReportEditorWidget

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    editor = ReportEditorWidget()
    qtbot.addWidget(editor)
    editor.edit_name.setText("Synthetic Report")
    before = set(config.get_reports_dir().glob("*.json"))
    bundled_before = set((AppConfig.BUNDLED_RESOURCES_DIR / "reports").glob("*.json"))

    editor.save_report()

    assert len(set(config.get_reports_dir().glob("*.json")) - before) == 1
    assert set((AppConfig.BUNDLED_RESOURCES_DIR / "reports").glob("*.json")) == bundled_before
