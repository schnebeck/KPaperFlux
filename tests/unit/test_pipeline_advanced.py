"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_pipeline_advanced.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Native text layer detection and extraction of Stage 0 with
                generated PDFs (one with a text layer, one image-only).
------------------------------------------------------------------------------
"""
from pathlib import Path
from unittest.mock import MagicMock

import fitz
import pytest
from reportlab.pdfgen import canvas

from core.pipeline import PipelineProcessor


@pytest.fixture
def pipeline() -> PipelineProcessor:
    return PipelineProcessor(vault=MagicMock(), db=MagicMock())


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "native.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(72, 760, "Synthetic invoice page one")
    c.showPage()
    c.drawString(72, 760, "Synthetic invoice page two")
    c.save()
    return path


@pytest.fixture
def image_pdf(tmp_path: Path) -> Path:
    """A 'scan': one page with an image and no text layer."""
    path = tmp_path / "scan.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
        pix.clear_with(200)
        page.insert_image(page.rect, pixmap=pix)
        doc.save(str(path))
    return path


def test_text_layer_is_detected(pipeline, text_pdf, image_pdf):
    assert pipeline._is_native_pdf(text_pdf) is True
    assert pipeline._is_native_pdf(image_pdf) is False


def test_unreadable_file_counts_as_not_native(pipeline, tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    assert pipeline._is_native_pdf(broken) is False


def test_native_text_is_extracted_per_page(pipeline, text_pdf, image_pdf):
    assert pipeline._extract_text_native(text_pdf) == {
        "1": "Synthetic invoice page one", "2": "Synthetic invoice page two"}
    assert pipeline._extract_text_native(image_pdf) == {}
