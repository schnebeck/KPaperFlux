"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/gui/test_pdf_viewer_resources.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    The PDF viewer leaves no document copies in the temp directory
                and closes the documents it replaces.
------------------------------------------------------------------------------
"""
import tempfile
from pathlib import Path

import fitz
import pytest
from reportlab.pdfgen import canvas

from core.database import DatabaseManager
from core.models.physical import PhysicalFile
from core.models.virtual import SourceReference, VirtualDocument
from core.pipeline import PipelineProcessor
from core.repositories.logical_repo import LogicalRepository
from core.repositories.physical_repo import PhysicalRepository
from core.vault import DocumentVault
from gui.pdf_viewer import PdfViewerWidget

DOC_UUID = "11111111-2222-4333-8444-555555555555"
FILE_UUID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


@pytest.fixture
def pipeline(tmp_path) -> PipelineProcessor:
    db = DatabaseManager(str(tmp_path / "viewer.db"))
    db.init_db()
    vault = DocumentVault(str(tmp_path / "vault"))
    original = Path(vault.base_path) / f"{FILE_UUID}.pdf"
    c = canvas.Canvas(str(original))
    c.drawString(72, 760, "Synthetic page")
    c.save()
    PhysicalRepository(db).save(PhysicalFile(uuid=FILE_UUID, original_filename="s.pdf", file_path=str(original)))
    LogicalRepository(db).save(VirtualDocument(uuid=DOC_UUID,
                                               source_mapping=[SourceReference(file_uuid=FILE_UUID, pages=[1])]))
    return PipelineProcessor(vault=vault, db=db)


def _temp_copies() -> set:
    return set(Path(tempfile.gettempdir()).glob("kview_*.pdf"))


def test_viewing_documents_leaves_no_temp_copies(qtbot, pipeline):
    viewer = PdfViewerWidget(pipeline=pipeline)
    qtbot.addWidget(viewer)
    before = _temp_copies()

    viewer.load_document(DOC_UUID)
    viewer.load_document(DOC_UUID)

    assert viewer.canvas.doc is not None and viewer.canvas.doc.page_count == 1
    assert _temp_copies() == before


def test_canvas_closes_replaced_document(qtbot, pipeline):
    viewer = PdfViewerWidget(pipeline=pipeline)
    qtbot.addWidget(viewer)
    viewer.load_document(DOC_UUID)
    first = viewer.canvas.doc

    viewer.load_document(DOC_UUID)

    assert first.is_closed
    viewer.clear()
    assert viewer.canvas.doc is None


def _rendered_sizes(canvas, monkeypatch) -> list:
    """Sizes of the pixmaps fitz renders (QLabel.pixmap() returns a display-scaled copy)."""
    sizes = []
    original = fitz.Page.get_pixmap

    def spy(page, *args, **kwargs):
        pix = original(page, *args, **kwargs)
        sizes.append((pix.width, pix.height))
        return pix
    monkeypatch.setattr(fitz.Page, "get_pixmap", spy)
    return sizes


def test_render_size_is_bounded_at_high_zoom(qtbot, pipeline, monkeypatch):
    viewer = PdfViewerWidget(pipeline=pipeline)
    qtbot.addWidget(viewer)
    viewer.load_document(DOC_UUID)
    canvas = viewer.canvas
    page = canvas.doc[0]
    sizes = _rendered_sizes(canvas, monkeypatch)

    canvas.zoom_factor = 10.0
    canvas.render_current_page()

    width, height = sizes[-1]
    assert width * height <= canvas.MAX_RENDER_PIXELS * 1.01  # fitz rounds up to whole pixels
    # The logical size still follows the zoom, so selections map to the right place
    assert canvas.display_label.width() == pytest.approx(page.rect.width * 10, abs=2)


def test_normal_zoom_keeps_full_supersampling(qtbot, pipeline, monkeypatch):
    viewer = PdfViewerWidget(pipeline=pipeline)
    qtbot.addWidget(viewer)
    viewer.load_document(DOC_UUID)
    canvas = viewer.canvas
    page = canvas.doc[0]
    sizes = _rendered_sizes(canvas, monkeypatch)

    canvas.zoom_factor = 1.0
    canvas.render_current_page()

    expected = canvas.devicePixelRatioF() * canvas.SUPERSAMPLING
    assert sizes[-1][0] == pytest.approx(page.rect.width * expected, abs=2)
    assert canvas.display_label.width() == pytest.approx(page.rect.width, abs=2)
