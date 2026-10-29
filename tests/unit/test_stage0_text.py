"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_stage0_text.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Stage 0 text extraction: no OCR run when the analysis engine
                delivers the text layer (library and REST mode).
                Uses generated digital and image-only (scan) PDFs.
------------------------------------------------------------------------------
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from core.database import DatabaseManager
from core.pipeline import PipelineProcessor
from core.vault import DocumentVault, searchable_path_for


@pytest.fixture
def digital_pdf(tmp_path: Path) -> Path:
    """Two pages with a real text layer."""
    path = tmp_path / "digital.pdf"
    doc = fitz.open()
    for index in range(2):
        doc.new_page().insert_text((72, 72), f"digital text {index + 1}")
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def scan_pdf(tmp_path: Path) -> Path:
    """One image-only page (no fonts), like a scanner output."""
    path = tmp_path / "scan.pdf"
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 100), False)
    pix.clear_with(200)
    doc = fitz.open()
    doc.new_page().insert_image(fitz.Rect(72, 72, 272, 172), pixmap=pix)
    doc.save(str(path))
    doc.close()
    return path


def _pipeline(tmp_path: Path, mode: str) -> PipelineProcessor:
    """Pipeline on a temporary vault and in-memory DB with the given FluxSense mode."""
    db = DatabaseManager(":memory:")
    db.init_db()
    pipeline = PipelineProcessor(vault=DocumentVault(tmp_path / "vault"), db=db)
    pipeline.config = MagicMock()
    pipeline.config.get_fluxsense_mode.return_value = mode
    pipeline.config.get_ocr_engine.return_value = "ocrmypdf"
    return pipeline


def test_library_mode_scan_gets_no_stage0_ocr(tmp_path: Path, scan_pdf: Path) -> None:
    """Scans are not OCRed in Stage 0: FluxSense delivers their text; no derived searchable PDF."""
    pipeline = _pipeline(tmp_path, "library")
    with patch.object(pipeline, "_run_ocr") as run_ocr:
        phys = pipeline._ingest_physical_file(str(scan_pdf))
    run_ocr.assert_not_called()
    assert phys.raw_ocr_data == {}
    assert phys.page_count_phys == 1
    assert not searchable_path_for(phys.file_path).exists()


def test_library_mode_digital_keeps_native_text(tmp_path: Path, digital_pdf: Path) -> None:
    """Digital PDFs keep their exact native text layer."""
    pipeline = _pipeline(tmp_path, "library")
    with patch.object(pipeline, "_run_ocr") as run_ocr:
        phys = pipeline._ingest_physical_file(str(digital_pdf))
    run_ocr.assert_not_called()
    assert phys.raw_ocr_data == {"1": "digital text 1", "2": "digital text 2"}


def test_rest_mode_also_skips_stage0_ocr(tmp_path: Path, scan_pdf: Path) -> None:
    """REST responses carry the text layer too (include_page_text), so Stage 0 never OCRs."""
    pipeline = _pipeline(tmp_path, "rest")
    with patch.object(pipeline, "_run_ocr") as run_ocr:
        phys = pipeline._ingest_physical_file(str(scan_pdf))
    run_ocr.assert_not_called()
    assert phys.raw_ocr_data == {}


def test_explicit_force_ocr_is_unchanged(tmp_path: Path, scan_pdf: Path) -> None:
    """'Force OCR / Searchable PDF' still runs OCR (and produces the derived searchable copy)."""
    pipeline = _pipeline(tmp_path, "library")
    with patch.object(pipeline, "_run_ocr", return_value={"1": "forced"}) as run_ocr:
        assert pipeline._extract_text_map(scan_pdf, force_ocr=True) == {"1": "forced"}
    run_ocr.assert_called_once()
