
import pytest
import os
from core.stamper import DocumentStamper
import pikepdf
from reportlab.pdfgen import canvas
from pathlib import Path

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
