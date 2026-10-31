"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_resource_paths.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Bundled resources load regardless of the working directory;
                imported report ids cannot write outside the reports folder;
                broken rows do not end up as None in document lists.
------------------------------------------------------------------------------
"""
import json

from core.metadata_normalizer import MetadataNormalizer
from core.paths import RESOURCES_DIR


def test_resources_load_from_another_working_directory(tmp_path, monkeypatch, qapp):
    from gui.delegates.tag_delegate import TagDelegate

    monkeypatch.chdir(tmp_path)
    MetadataNormalizer._config = None

    expected = json.loads((RESOURCES_DIR / "tag_styles.json").read_text(encoding="utf-8"))
    assert TagDelegate()._load_styles() == expected
    assert MetadataNormalizer.get_config() == json.loads(
        (RESOURCES_DIR / "type_definitions.json").read_text(encoding="utf-8"))


def test_imported_report_id_cannot_escape_the_reports_dir(qtbot, tmp_path):
    from unittest.mock import MagicMock
    from core.database import DatabaseManager
    from gui.reporting import ReportingWidget

    widget = ReportingWidget(db_manager=MagicMock(spec=DatabaseManager))
    qtbot.addWidget(widget)
    widget.report_dir = str(tmp_path / "reports")
    (tmp_path / "reports").mkdir()

    assert widget._save_report_definition({"id": "../../escaped", "name": "Synthetic"})

    assert not (tmp_path / "escaped.json").exists()
    assert (tmp_path / "reports" / "escaped.json").exists()


def test_unhydratable_rows_are_skipped(tmp_path):
    from core.database import DatabaseManager
    db = DatabaseManager(str(tmp_path / "rows.db"))
    db.init_db()
    db.connection.execute("INSERT INTO virtual_documents (uuid, source_mapping, deleted, archived) "
                          "VALUES ('ok', '[]', 0, 0), ('broken', '[{\"pages\": \"x\"}]', 0, 0)")
    db.connection.commit()

    docs = db.search_documents_advanced({})

    assert [d.uuid for d in docs] == ["ok"]
