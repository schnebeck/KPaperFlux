
import pytest
import os
import fitz
import pikepdf
from unittest.mock import MagicMock, patch
from core.utils.forensics import get_pdf_class, PDFClass
from core.utils.hybrid_handler import prepare_hybrid_container, restore_zugferd_xml
from core.stamper import DocumentStamper
from reportlab.pdfgen import canvas

@pytest.fixture
def sample_pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(100, 100, "Normal PDF")
    c.save()
    return str(path)

@pytest.fixture
def zugferd_pdf(tmp_path):
    path = tmp_path / "zugferd.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.embfile_add("factur-x.xml", b"<xml>test</xml>", filename="factur-x.xml")
    doc.save(str(path))
    doc.close()
    return str(path)

def test_forensics_standard(sample_pdf):
    assert get_pdf_class(sample_pdf) == PDFClass.STANDARD

def test_forensics_zugferd(zugferd_pdf):
    assert get_pdf_class(zugferd_pdf) == PDFClass.ZUGFERD

@patch("fitz.open")
def test_forensics_signed(mock_open, sample_pdf):
    mock_doc = MagicMock()
    # Mock sig_flags as a property or method depending on version
    mock_doc.get_sigflags.return_value = 1
    mock_doc.embfile_count.return_value = 0
    mock_open.return_value = mock_doc
    
    assert get_pdf_class(sample_pdf) == PDFClass.SIGNED

def test_hybrid_handler_envelope_creation(sample_pdf, tmp_path):
    # We mock the class as SIGNED to trigger envelope
    output = str(tmp_path / "hybrid.pdf")
    
    with patch("core.utils.hybrid_handler.get_pdf_class", return_value=PDFClass.SIGNED):
        success = prepare_hybrid_container(sample_pdf, output)
        assert success is True
        assert os.path.exists(output)
        
        # Verify the envelope contains the original as attachment
        doc = fitz.open(output)
        assert doc.embfile_count() == 1
        assert doc.embfile_info(0)["name"] == "original_signed_source.pdf"
        assert "kpaperflux_immutable" in doc.metadata.get("keywords", "")
        doc.close()

def test_restore_zugferd_xml(zugferd_pdf, sample_pdf, tmp_path):
    # target is a simple pdf, we want to inject xml from original
    target = str(tmp_path / "target.pdf")
    import shutil
    shutil.copy2(sample_pdf, target)
    
    success = restore_zugferd_xml(zugferd_pdf, target)
    assert success is True
    
    doc = fitz.open(target)
    assert doc.embfile_count() == 1
    assert doc.embfile_info(0)["name"] == "factur-x.xml"
    doc.close()

def test_stamper_integration_class_a(sample_pdf, tmp_path):
    # Test that apply_stamp creates a hybrid if source is Class A
    stamper = DocumentStamper()
    output = str(tmp_path / "stamped_hybrid.pdf")
    
    with patch("core.stamper.get_pdf_class", return_value=PDFClass.SIGNED), \
         patch("core.utils.hybrid_handler.get_pdf_class", return_value=PDFClass.SIGNED):
        stamper.apply_stamp(sample_pdf, output, "APPROVED")
        
        assert os.path.exists(output)
        # Should be a hybrid container (check keyword)
        doc = fitz.open(output)
        assert "kpaperflux_immutable" in doc.metadata.get("keywords", "")
        assert doc.embfile_count() == 1 # The original
        doc.close()

def test_stamper_integration_class_b(zugferd_pdf, tmp_path):
    # Test that apply_stamp preserves ZUGFeRD XML for Class B
    stamper = DocumentStamper()
    output = str(tmp_path / "stamped_zugferd.pdf")
    
    stamper.apply_stamp(zugferd_pdf, output, "PAID")
    
    assert os.path.exists(output)
    doc = fitz.open(output)
    # Should STILL have ZUGFeRD XML
    has_xml = False
    for i in range(doc.embfile_count()):
        if doc.embfile_info(i)["name"].lower() == "factur-x.xml":
            has_xml = True
            break
    assert has_xml is True
    doc.close()
