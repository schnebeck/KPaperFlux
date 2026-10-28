"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_ocr_worm.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Verifies the vault WORM rule for OCR: ocrmypdf runs on a temp
                copy, the original is never modified, and the searchable
                result is stored as a separate derived artifact.
------------------------------------------------------------------------------
"""

import hashlib
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

from core.pipeline import PipelineProcessor
from core.vault import remove_derived_files, resolve_view_path, searchable_path_for

ORIGINAL_BYTES = b"%PDF-1.4 original scan"
OCR_BYTES = b"%PDF-1.4 searchable sandwich"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def pipeline() -> PipelineProcessor:
    proc = PipelineProcessor.__new__(PipelineProcessor)
    proc.config = MagicMock()
    proc.config.get_ocr_binary.return_value = "ocrmypdf"
    proc.current_process = None
    return proc


def _fake_ocrmypdf(calls: List[List[str]]) -> Any:
    def popen(cmd: List[str], **_kwargs: Any) -> MagicMock:
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(OCR_BYTES)  # ocrmypdf writes its output file
        proc = MagicMock()
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        return proc
    return popen


def test_run_ocr_never_modifies_vault_original(pipeline: PipelineProcessor, tmp_path: Path) -> None:
    original = tmp_path / "1234.pdf"
    original.write_bytes(ORIGINAL_BYTES)
    digest = _sha(original)
    calls: List[List[str]] = []
    seen_paths: List[Path] = []

    def fake_extract(path: Path) -> dict:
        seen_paths.append(path)
        return {"1": "OCR Text"}

    with patch("core.pipeline.subprocess.Popen", side_effect=_fake_ocrmypdf(calls)), \
         patch.object(pipeline, "_extract_text_native", side_effect=fake_extract):
        result = pipeline._run_ocr(original)

    assert result == {"1": "OCR Text"}
    assert _sha(original) == digest
    # ocrmypdf got a temp copy as input, never the vault file
    assert Path(calls[0][-2]) != original
    assert calls[0][-2].endswith("input_1234.pdf")
    # Text was extracted from the OCR output, not from the original
    assert seen_paths[0] != original
    # The searchable copy is stored as derived artifact
    derived = searchable_path_for(original)
    assert derived == tmp_path / "derived" / "1234.searchable.pdf"
    assert derived.read_bytes() == OCR_BYTES


def test_run_ocr_without_storing_searchable(pipeline: PipelineProcessor, tmp_path: Path) -> None:
    original = tmp_path / "abcd.pdf"
    original.write_bytes(ORIGINAL_BYTES)
    with patch("core.pipeline.subprocess.Popen", side_effect=_fake_ocrmypdf([])), \
         patch.object(pipeline, "_extract_text_native", return_value={"1": "x"}):
        pipeline._run_ocr(original, store_searchable=False)
    assert not searchable_path_for(original).exists()
    assert original.read_bytes() == ORIGINAL_BYTES


def test_resolve_view_path_and_cleanup(tmp_path: Path) -> None:
    original = tmp_path / "5678.pdf"
    original.write_bytes(ORIGINAL_BYTES)
    assert resolve_view_path(original) == str(original)

    derived = searchable_path_for(original)
    derived.parent.mkdir()
    derived.write_bytes(OCR_BYTES)
    assert resolve_view_path(original) == str(derived)

    remove_derived_files(original)
    assert not derived.exists()
    assert original.exists()


def test_integrity_scan_ignores_derived_artifacts(tmp_path: Path) -> None:
    from core.integrity import IntegrityManager

    (tmp_path / "1111.pdf").write_bytes(ORIGINAL_BYTES)
    (tmp_path / "derived").mkdir()
    (tmp_path / "derived" / "1111.searchable.pdf").write_bytes(OCR_BYTES)

    manager = IntegrityManager.__new__(IntegrityManager)
    manager.vault = MagicMock(base_path=tmp_path)
    manager.logic_repo = MagicMock()
    manager.logic_repo.get_all.return_value = []
    manager.phys_repo = MagicMock()
    manager.phys_repo.get_all.return_value = []

    ghosts = manager.check_integrity().ghosts
    assert [g.name for g in ghosts] == ["1111.pdf"]
