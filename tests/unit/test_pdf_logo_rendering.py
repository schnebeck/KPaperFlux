
import unittest
import os
import fitz
import numpy as np
from pathlib import Path
from core.pdf_renderer import ProfessionalPdfRenderer
from core.models.semantic import SemanticExtraction, MetaHeader, AddressInfo, FinanceBody

class TestPdfLogoRendering(unittest.TestCase):
    def setUp(self):
        self.output_pdf = "tests/unit/test_logo_output.pdf"
        self.logo_dir = Path("/home/schnebeck/Dokumente/Projects/KPaperFlux/tests/resources/demo_invoices_complex/logos")
        self.logos = list(self.logo_dir.glob("*.png"))
        
    def test_logo_presence_and_visibility(self):
        if not self.logos:
            self.skipTest("No logos found in tests/resources/demo_invoices_complex/logos")
            
        # Select a logo that is likely to have colored pixels
        logo_path = str(self.logos[0])
        print(f"Testing with logo: {os.path.basename(logo_path)}")
        
        renderer = ProfessionalPdfRenderer(self.output_pdf, locale="de")
        renderer.set_style(concept="MODERN", logo=logo_path)
        
        # Create minimal data
        data = SemanticExtraction(
            direction="INBOUND",
            tenant_context="BUSINESS",
            meta_header=MetaHeader(
                sender=AddressInfo(name="Logo Test Corp", city="Berlin"),
                recipient=AddressInfo(name="Recipient"),
                doc_date="2026-02-12",
                doc_number="TEST-001"
            ),
            bodies={"finance_body": FinanceBody(currency="EUR")}
        )
        
        renderer.render_document(data)
        
        # 1. Structural Verification (PDF Objects)
        self.assertTrue(os.path.exists(self.output_pdf), "PDF was not generated")
        doc = fitz.open(self.output_pdf)
        page = doc[0]
        images = page.get_images(full=True)
        self.assertTrue(len(images) > 0, "No image object found in PDF structure")
        
        xref = images[0][0]
        rects = page.get_image_rects(xref)
        self.assertTrue(len(rects) > 0, "Image has no valid bounding box on page")
        logo_rect = rects[0]
        
        # 2. Visual Verification (Bitmap Rendering)
        # Render the page to a pixmap (bitmap)
        pix = page.get_pixmap(colorspace=fitz.csRGB)
        
        # Convert to numpy for easier pixel manipulation if needed, 
        # or just check the pixmap data.
        # pix.samples contains the raw RGB data.
        
        # We define a small sub-area inside the logo_rect to check for "ink"
        # coordinates in points need to be scaled to pixels
        # Default resolution is 72 dpi, so 1 point = 1 pixel at scale 1.
        
        # Get a sample coordinate inside the logo rect
        sample_x = int(logo_rect.x0 + logo_rect.width / 2)
        sample_y = int(logo_rect.y0 + logo_rect.height / 2)
        
        # Ensure coordinates are within pixmap bounds
        sample_x = max(0, min(sample_x, pix.width - 1))
        sample_y = max(0, min(sample_y, pix.height - 1))
        
        # Check a 10x10 block for non-white pixels
        found_content = False
        non_white_count = 0
        for y in range(max(0, sample_y-5), min(pix.height, sample_y+5)):
            for x in range(max(0, sample_x-5), min(pix.width, sample_x+5)):
                # RGB values
                p = pix.pixel(x, y)
                if p != (255, 255, 255):
                    non_white_count += 1
        
        doc.close()
        
        print(f"Logo Rect: {logo_rect}")
        print(f"Non-white pixels in center 10x10 block: {non_white_count}")
        
        # Final cleanup
        if os.path.exists(self.output_pdf):
             os.remove(self.output_pdf)

        # Assertions
        self.assertGreater(non_white_count, 0, f"The logo area at {logo_rect} appears to be empty/white in the rendered bitmap!")
        print("Final Verification: Logo is physically present and visible in the rendered bitmap.")

if __name__ == "__main__":
    unittest.main()
