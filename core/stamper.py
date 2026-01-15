
import io
from pathlib import Path
from typing import Tuple, Optional
import pikepdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

class DocumentStamper:
    """
    Applies text tokens/stamps to PDF documents.
    """
    
    def apply_stamp(self, input_path: str, output_path: str, text: str, 
                   position: str = "top-right", 
                   color: Tuple[int, int, int] = (255, 0, 0),
                   rotation: int = 45):
        """
        Apply a text stamp to the PDF.
        position: 'top-left', 'top-right', 'center', 'bottom-left', 'bottom-right'
        color: (r, g, b) 0-255.
        """
        
        try:
            target_pdf = pikepdf.Pdf.open(input_path)
            if len(target_pdf.pages) == 0:
                return

            first_page = target_pdf.pages[0]
            # Get dimensions (default to A4 usually if missing, but PDF pages usually have MediaBox)
            # MediaBox is list [x, y, w, h]
            mediabox = first_page.MediaBox
            page_w = float(mediabox[2])
            page_h = float(mediabox[3])
            
            # Calculate coordinates
            x, y = 100, 100 # Default
            margin = 50
            
            if position == "top-left":
                x = margin
                y = page_h - margin - 100
            elif position == "top-right":
                x = page_w - margin - 150
                y = page_h - margin - 100
            elif position == "center":
                x = page_w / 2 - 50
                y = page_h / 2
                rotation = 45
            elif position == "bottom-left":
                x = margin
                y = margin
            elif position == "bottom-right":
                x = page_w - margin - 150
                y = margin
            
            # 1. Create Stamp PDF
            packet = io.BytesIO()
            # Create canvas with SAME sizing as page to simplify overlay
            can = canvas.Canvas(packet, pagesize=(page_w, page_h))
            
            # Set color
            r, g, b = [c/255.0 for c in color]
            can.setFillColorRGB(r, g, b, 0.5) # 0.5 alpha
            
            can.setFont("Helvetica-Bold", 30)
            
            # Move to position and rotate
            can.saveState()
            can.translate(x, y)
            can.rotate(rotation)
            can.drawString(0, 0, text)
            can.restoreState()
            
            can.save()
            packet.seek(0)
            
            # 2. Open Stamp
            stamp_pdf = pikepdf.Pdf.open(packet)
            stamp_page = stamp_pdf.pages[0]
            
            # 3. Overlay
            # Use Rectangle matching page size since canvas matched page size
            first_page.add_overlay(stamp_page, pikepdf.Rectangle(0, 0, page_w, page_h)) 
                
            target_pdf.save(output_path)
            
        except Exception as e:
            print(f"Stamping error: {e}")
            raise
