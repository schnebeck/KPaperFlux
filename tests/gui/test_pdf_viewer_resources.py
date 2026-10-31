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
