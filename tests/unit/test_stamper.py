"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_stamper.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Tests: stamper.
------------------------------------------------------------------------------
"""

import pytest
from core.stamper import DocumentStamper
import pikepdf
from reportlab.pdfgen import canvas

@pytest.fixture
def create_pdf(tmp_path):
    path = tmp_path / "test.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(100, 100, "Original Content")
    c.save()
    return path

def test_stamper_apply(create_pdf, tmp_path):
    stamper = DocumentStamper()
    output = tmp_path / "stamped.pdf"
    
    stamper.apply_stamp(str(create_pdf), str(output), "STAMPED", position="center")
    
    assert output.exists()
    
    # Verify content? Hard with PikePDF to read text easily without extraction.
    # But we can check page count or file size increase.
    # Or just that it's a valid PDF.
    
    pdf = pikepdf.Pdf.open(output)
    assert len(pdf.pages) == 1
    
    # Check if Resources XObject has a Form (the stamp)
    # page.resources['/XObject'] should have an entry
    page = pdf.pages[0]
    assert "/XObject" in page.resources


def _red_pixels(pdf_path) -> int:
    import fitz
    with fitz.open(str(pdf_path)) as doc:
        pix = doc[0].get_pixmap(dpi=40)
    samples, n = pix.samples, pix.n
    return sum(1 for i in range(0, len(samples), n)
               if samples[i] > 200 and samples[i + 1] < 80 and samples[i + 2] < 80)


def test_stamp_is_visible_when_rendered(create_pdf, tmp_path):
    output = tmp_path / "stamped.pdf"
    assert _red_pixels(create_pdf) == 0

    DocumentStamper().apply_stamp(str(create_pdf), str(output), "PAID", position="center")

    assert _red_pixels(output) > 20


def _red_centroid(pdf_path) -> tuple:
    import fitz
    with fitz.open(str(pdf_path)) as doc:
        pix = doc[0].get_pixmap(dpi=40)
    samples, n, xs, ys = pix.samples, pix.n, [], []
    for i in range(0, len(samples), n):
        if samples[i] > 200 and samples[i + 1] < 80 and samples[i + 2] < 80:
            xs.append((i // n) % pix.width)
            ys.append((i // n) // pix.width)
    return sum(xs) / len(xs), sum(ys) / len(ys)


def test_stamp_position_ignores_unbalanced_page_content(create_pdf, tmp_path):
    """A page that leaves a scaling active must not move the stamp."""
    unbalanced = tmp_path / "unbalanced.pdf"
    with pikepdf.Pdf.open(create_pdf) as pdf:
        page = pdf.pages[0]
        page.Contents = pikepdf.Array([page.Contents, pdf.make_stream(b"0.5 0 0 0.5 0 0 cm")])
        pdf.save(unbalanced)
    normal_out, unbalanced_out = tmp_path / "normal_out.pdf", tmp_path / "unbalanced_out.pdf"
    stamper = DocumentStamper()
    stamper.apply_stamp(str(create_pdf), str(normal_out), "PAID", position="center")
    stamper.apply_stamp(str(unbalanced), str(unbalanced_out), "PAID", position="center")

    nx, ny = _red_centroid(normal_out)
    ux, uy = _red_centroid(unbalanced_out)
    assert abs(nx - ux) < 3 and abs(ny - uy) < 3
