
import pytest
import shutil
import uuid
import pikepdf
from pathlib import Path
from core.stamper import DocumentStamper

class TestStamperOverlayRemoval:
    @pytest.fixture
    def stamper(self):
        return DocumentStamper()

    @pytest.fixture
    def input_pdf(self, tmp_path):
        pdf_path = tmp_path / "input.pdf"
        pdf = pikepdf.new()
        pdf.add_blank_page(page_size=(200, 200))
        pdf.save(str(pdf_path))
        return pdf_path

    @pytest.fixture
    def output_pdf(self, tmp_path):
        return tmp_path / "output.pdf"

    def test_apply_and_remove_overlay_stamp(self, stamper, input_pdf, output_pdf):
        # 1. Apply Stamp
        text = "TEST_STAMP"
        stamper.apply_stamp(str(input_pdf), str(output_pdf), text)
        
        # 2. Verify Stamp Exists
        assert stamper.has_stamp(str(output_pdf))
        stamps = stamper.get_stamps(str(output_pdf))
        assert len(stamps) == 1
        assert stamps[0]['text'] == text
        stamp_id = stamps[0]['id']
        assert stamp_id is not None
        
        # 3. Remove Stamp
        success = stamper.remove_stamp(str(output_pdf), stamp_id)
        assert success
        
        # 4. Verify Removal
        assert not stamper.has_stamp(str(output_pdf))
        stamps_after = stamper.get_stamps(str(output_pdf))
        assert len(stamps_after) == 0
        
        # 5. Verify PDF Structure (Content Stream)
        pdf = pikepdf.Pdf.open(str(output_pdf))
        page = pdf.pages[0]
        # Check that Resource is gone
        if "/Resources" in page and "/XObject" in page.Resources:
            for name in page.Resources.XObject.keys():
                assert "KPaperFlux" not in str(name)

    def test_remove_specific_stamp(self, stamper, input_pdf, output_pdf):
        # Apply two stamps
        text1 = "Stamp1"
        text2 = "Stamp2"
        stamper.apply_stamp(str(input_pdf), str(output_pdf), text1, position="top-right")
        # Apply second to same output (read output as input)
        stamper.apply_stamp(str(output_pdf), str(output_pdf), text2, position="bottom-left")
        
        stamps = stamper.get_stamps(str(output_pdf))
        assert len(stamps) == 2
        
        id1 = [s['id'] for s in stamps if s['text'] == text1][0]
        
        # Remove Stamp 1 only
        stamper.remove_stamp(str(output_pdf), id1)
        
        stamps_after = stamper.get_stamps(str(output_pdf))
        assert len(stamps_after) == 1
        assert stamps_after[0]['text'] == text2
