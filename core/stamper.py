"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/stamper.py
Version:        1.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Applies persistent and manageable text tokens/stamps to PDF 
                documents using Form XObjects. Supports rotation-aware 
                positioning, stamp management, and safe removal.
------------------------------------------------------------------------------
"""

import io
import uuid
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pikepdf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


class DocumentStamper:
    """
    Applies text tokens/stamps to PDF documents using Manual Overlay (Form XObject + Do command).
    This guarantees visibility (like add_overlay) but allows management/removal.
    """

    def apply_stamp(
        self,
        input_path: str,
        output_path: str,
        text: str,
        position: str = "top-right",
        color: Tuple[int, int, int] = (255, 0, 0),
        rotation: int = 45
    ) -> None:
        """
        Applies a text stamp to the first page of a PDF.

        Args:
            input_path: Path to the source PDF.
            output_path: Path where the stamped PDF should be saved.
            text: The text to stamp. Use 'DEBUG_RECT' for a placeholder rectangle.
            position: Keyword for placement ('top-left', 'top-right', 'center', etc.).
            color: RGB color tuple (0-255).
            rotation: Rotation in degrees (clockwise).
        """
        try:
            target_pdf = pikepdf.Pdf.open(input_path, allow_overwriting_input=True)
            if len(target_pdf.pages) == 0:
                print("[Stamper] No pages in target PDF")
                return

            first_page = target_pdf.pages[0]
            mediabox = list(first_page.MediaBox)
            page_w = float(mediabox[2])
            page_h = float(mediabox[3])

            # Check Page Rotation
            page_rot = 0
            if "/Rotate" in first_page:
                try:
                    page_rot = int(first_page.Rotate)
                except (ValueError, TypeError):
                    pass

            # Normalize to 0-360 positive
            page_rot = page_rot % 360

            # Dimensions in Visual Space
            if page_rot in [90, 270]:
                vis_w, vis_h = page_h, page_w
            else:
                vis_w, vis_h = page_w, page_h

            # 1. Calc Visual Coordinates (relative to visual page appearance)
            vx, vy = 100.0, 100.0
            margin = 50.0
            if position == "top-left":
                vx, vy = margin, vis_h - margin - 100
            elif position == "top-right":
                vx, vy = vis_w - margin - 150, vis_h - margin - 100
            elif position == "top-center":
                vx, vy = vis_w / 2 - 75, vis_h - margin - 100
            elif position == "center":
                vx, vy = vis_w / 2 - 50, vis_h / 2
            elif position == "bottom-left":
                vx, vy = margin, margin
            elif position == "bottom-right":
                vx, vy = vis_w - margin - 150, margin
            elif position == "bottom-center":
                vx, vy = vis_w / 2 - 75, margin

            # 2. Map Visual(vx,vy) -> Geometric(gx, gy) based on PDF rotation
            gx, gy = vx, vy
            if page_rot == 90:
                gx = page_w - vy
                gy = vx
            elif page_rot == 180:
                gx = page_w - vx
                gy = page_h - vy
            elif page_rot == 270:
                gx = vy
                gy = page_h - vx

            # 3. Create Stamp PDF with ReportLab
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(page_w, page_h))
            r, g, b = [c / 255.0 for c in color]
            can.setFillColorRGB(r, g, b, 1.0)

            font_size = 30
            can.setFont("Helvetica-Bold", font_size)

            can.saveState()
            can.translate(gx, gy)

            # Compensate Page Rotation + Apply User Rotation
            final_rot = rotation - page_rot
            can.rotate(final_rot)

            if text == "DEBUG_RECT":
                can.rect(-50, -25, 100, 50, fill=1, stroke=0)
            else:
                lines = text.split('\n')
                lh = font_size * 1.2
                cy = 0.0
                for line in lines:
                    can.drawString(0, cy, line)
                    cy -= lh

            can.restoreState()
            can.save()
            packet.seek(0)

            # 4. Integrate into Target PDF
            stamp_pdf = pikepdf.Pdf.open(packet)
            stamp_page = stamp_pdf.pages[0]

            # Coalesce stamp content to a single stream
            contents_data = b""
            if "/Contents" in stamp_page:
                contents_data = stamp_page.contents_coalesce()

            # Create Form XObject in destination PDF
            form_xobj = target_pdf.make_stream(contents_data)
            form_xobj.Type = pikepdf.Name.XObject
            form_xobj.Subtype = pikepdf.Name.Form
            form_xobj.FormType = 1
            form_xobj.BBox = list(stamp_page.MediaBox)
            form_xobj.Matrix = [1, 0, 0, 1, 0, 0]

            # Copy resources (Fonts, etc.)
            if "/Resources" in stamp_page:
                new_res = pikepdf.Dictionary()
                for k, v in stamp_page.Resources.items():
                    try:
                        new_res[k] = target_pdf.copy_foreign(v)
                    except Exception:
                        new_res[k] = v
                form_xobj.Resources = new_res
            else:
                form_xobj.Resources = pikepdf.Dictionary()

            # Metadata for Management
            stamp_id = str(uuid.uuid4())
            xobj_name = f"KPaperFlux_{stamp_id}".replace("-", "")

            # Register in Page Resources
            if "/Resources" not in first_page:
                first_page.Resources = pikepdf.Dictionary()
            if "/XObject" not in first_page.Resources:
                first_page.Resources.XObject = pikepdf.Dictionary()

            first_page.Resources.XObject[f"/{xobj_name}"] = form_xobj

            # Tag XObject for later retrieval/removal
            form_xobj.KPaperFlux_Text = text
            form_xobj.KPaperFlux_ID = stamp_id

            # Append 'Do' operator to paint the XObject
            do_cmd_stream = target_pdf.make_stream(f"/{xobj_name} Do".encode())
            if "/Contents" not in first_page:
                first_page.Contents = do_cmd_stream
            else:
                if isinstance(first_page.Contents, (pikepdf.Array, list)):
                    first_page.Contents.append(do_cmd_stream)
                else:
                    first_page.Contents = pikepdf.Array([first_page.Contents, do_cmd_stream])

            target_pdf.save(output_path)
            target_pdf.close()
            stamp_pdf.close()

        except Exception as e:
            print(f"[Stamper] Stamping error: {e}")
            raise

    def get_stamps(self, file_path: str) -> List[Dict[str, str]]:
        """
        Retrieves a list of existing KPaperFlux stamps from a PDF.

        Args:
            file_path: Path to the PDF file.

        Returns:
            A list of dictionaries with 'id' and 'text'.
        """
        stamps: List[Dict[str, str]] = []
        try:
            with pikepdf.Pdf.open(file_path) as pdf:
                if len(pdf.pages) > 0:
                    page = pdf.pages[0]
                    if "/Resources" in page and "/XObject" in page.Resources:
                        xobjects = page.Resources.XObject
                        for name, xobj in xobjects.items():
                            if "/KPaperFlux_ID" in xobj:
                                s_id = str(xobj.KPaperFlux_ID)
                                text = str(xobj.KPaperFlux_Text) if "/KPaperFlux_Text" in xobj else ""
                                stamps.append({'id': s_id, 'text': text})
        except Exception as e:
            print(f"[Stamper] Error getting stamps: {e}")
            raise
        return stamps

    def has_stamp(self, file_path: str) -> bool:
        """Checks if a PDF contains any KPaperFlux stamps."""
        return len(self.get_stamps(file_path)) > 0

    def remove_stamp(self, file_path: str, stamp_id: Optional[str] = None) -> bool:
        """
        Removes KPaperFlux stamps from a PDF.

        Args:
            file_path: Path to the PDF file.
            stamp_id: Specific stamp ID to remove. If None, removes ALL KPaperFlux stamps.

        Returns:
            True if any stamps were removed, False otherwise.
        """
        try:
            with pikepdf.Pdf.open(file_path, allow_overwriting_input=True) as pdf:
                removed = False

                for page in pdf.pages:
                    if "/Resources" not in page or "/XObject" not in page.Resources:
                        continue

                    xobjects = page.Resources.XObject
                    names_to_remove: List[pikepdf.Name] = []

                    # 1. Identify XObjects to remove
                    for name, xobj in xobjects.items():
                        if "/KPaperFlux_ID" in xobj:
                            should_remove = False
                            if stamp_id:
                                if str(xobj.KPaperFlux_ID) == stamp_id:
                                    should_remove = True
                            else:
                                should_remove = True

                            if should_remove:
                                names_to_remove.append(pikepdf.Name(name))

                    if not names_to_remove:
                        continue

                    # 2. Cleanup Content Streams
                    if "/Contents" in page:
                        contents = page.Contents

                        if isinstance(contents, pikepdf.Array):
                            new_contents: List[Any] = []
                            for stream in contents:
                                data = stream.read_bytes()
                                is_stamp_stream = False
                                for n in names_to_remove:
                                    clean_name = str(n).replace("/", "")
                                    search_term = f"/{clean_name} Do".encode()
                                    if search_term in data:
                                        is_stamp_stream = True
                                        break
                                if not is_stamp_stream:
                                    new_contents.append(stream)
                            page.Contents = pikepdf.Array(new_contents)
                        else:
                            # Single stream. Parse and filter operators.
                            commands = pikepdf.parse_content_stream(page)
                            new_commands: List[Any] = []
                            for operands, operator in commands:
                                if operator == "Do" and operands:
                                    op_name = operands[0]
                                    if op_name in names_to_remove:
                                        continue
                                new_commands.append((operands, operator))
                            page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(new_commands))

                    # 3. Purge from Resources
                    for name in names_to_remove:
                        if name in xobjects:
                            del xobjects[name]

                    removed = True

                if removed:
                    pdf.save(file_path)
                    return True

                return False

        except Exception as e:
            print(f"[Stamper] Error removing stamp: {e}")
            raise
