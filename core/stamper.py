
import io
import uuid
import zlib
from pathlib import Path
from typing import Tuple, Optional, List, Dict
import pikepdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

class DocumentStamper:
    """
    Applies text tokens/stamps to PDF documents using Manual Overlay (Form XObject + Do command).
    This guarantees visibility (like add_overlay) but allows management/removal.
    """
    
    def apply_stamp(self, input_path: str, output_path: str, text: str, 
                   position: str = "top-right", 
                   color: Tuple[int, int, int] = (255, 0, 0),
                   rotation: int = 45):
        try:
            target_pdf = pikepdf.Pdf.open(input_path, allow_overwriting_input=True)
            if len(target_pdf.pages) == 0:
                print("DEBUG: No pages in target PDF")
                return

            first_page = target_pdf.pages[0]
            mediabox = list(first_page.MediaBox) # [0, 0, w, h] usually
            page_w = float(mediabox[2])
            page_h = float(mediabox[3])
            
            # Check Page Rotation
            page_rot = 0
            if "/Rotate" in first_page:
                try: page_rot = int(first_page.Rotate)
                except: pass
            
            # Normalize to 0-360 positive
            page_rot = page_rot % 360
            
            # Dimensions in Visual Space
            if page_rot in [90, 270]:
                vis_w, vis_h = page_h, page_w
            else:
                vis_w, vis_h = page_w, page_h
            
            # 1. Calc Visual Coordinates (Where we want it to APPEAR relative to visual page)
            vx, vy = 100, 100 
            margin = 50
            if position == "top-left":
                vx = margin; vy = vis_h - margin - 100
            elif position == "top-right":
                vx = vis_w - margin - 150; vy = vis_h - margin - 100
            elif position == "top-center":
                vx = vis_w / 2 - 75; vy = vis_h - margin - 100
            elif position == "center":
                vx = vis_w / 2 - 50; vy = vis_h / 2
            elif position == "bottom-left":
                vx = margin; vy = margin
            elif position == "bottom-right":
                vx = vis_w - margin - 150; vy = margin
            elif position == "bottom-center":
                vx = vis_w / 2 - 75; vy = margin
                
            # 2. Map Visual(vx,vy) -> Geometric(gx, gy) based on Rotation
            # ReportLab Canvas assumes Geometric Space (0..PageW, 0..PageH)
            gx, gy = vx, vy # Default 0
            
            if page_rot == 90:
                # 90 CW: Top=Left, Right=Top, Bottom=Right, Left=Bottom
                # Visual X axis maps to Geometric Y axis
                # Visual Y axis maps to Geometric -X axis ??
                # Map derived:
                # gx = page_w - vy? (Wait, page_w is VisH) -> gx = VisH - vy
                # gy = vx
                gx = page_w - vy # using page_w (geo width)
                gy = vx
                
                # Check: Vis Top-Right (vx=W, vy=H) -> gx=W-H? No.
                # Vis Top-Right (vx=VisW, vy=VisH) -> (GeoH, GeoW) 
                # (Remember VisW=GeoH, VisH=GeoW)
                # vx=GeoH, vy=GeoW
                # gx = GeoW - GeoW = 0.
                # gy = GeoH. 
                # -> (0, GeoH). This is Geo Top-Left.
                # 90CW: Geo Top-Left becomes Vis Top-Right. CORRECT. 
                
            elif page_rot == 180:
                gx = page_w - vx
                gy = page_h - vy
                
            elif page_rot == 270:
                # 270 CW (90 CCW)
                # gx = vy
                # gy = page_h - vx
                gx = vy
                gy = page_h - vx
            
            # ReportLab
            packet = io.BytesIO()
            # Canvas size must match Geometric Page Size
            can = canvas.Canvas(packet, pagesize=(page_w, page_h))
            r, g, b = [c/255.0 for c in color]
            can.setFillColorRGB(r, g, b, 1.0) # Alpha 1.0
            
            font_size = 30
            can.setFont("Helvetica-Bold", font_size)
            
            can.saveState()
            can.translate(gx, gy)
            
            # Compensate Rotation + Apply User Rotation
            # If Page is 90, we must rotate -90 to be upright.
            # Then add user rotation.
            final_rot = rotation - page_rot
            can.rotate(final_rot)
            
            if text == "DEBUG_RECT":
                can.rect(-50, -25, 100, 50, fill=1, stroke=0)
            else:
                lines = text.split('\n')
                lh = font_size * 1.2
                cy = 0
                for line in lines:
                    can.drawString(0, cy, line)
                    cy -= lh
            
            can.restoreState()
            can.save()
            packet.seek(0)
            
            stamp_pdf = pikepdf.Pdf.open(packet)
            stamp_page = stamp_pdf.pages[0]
            
            # Extract Content Data
            contents_data = b""
            if "/Contents" in stamp_page:
                contents = stamp_page.Contents
                if isinstance(contents, pikepdf.Array):
                    contents_data = stamp_page.contents_coalesce()
                else:
                    try:
                        raw = contents.read_bytes()
                        if "/Filter" in contents:
                             flt = contents.Filter
                             is_flate = False
                             if flt == pikepdf.Name("/FlateDecode"):
                                 is_flate = True
                             elif isinstance(flt, pikepdf.Array):
                                 if pikepdf.Name("/FlateDecode") in flt:
                                     is_flate = True
                             
                             if is_flate:
                                 try:
                                     contents_data = zlib.decompress(raw)
                                 except Exception:
                                     try:
                                         contents_data = zlib.decompress(raw, -15)
                                     except Exception:
                                         contents_data = raw
                             else:
                                 contents_data = raw
                        else:
                            contents_data = raw
                    except Exception:
                        contents_data = b""
            
            if not contents_data:
                contents_data = b""

            # Create Form XObject
            form_xobj = target_pdf.make_stream(contents_data)
            form_xobj.Type = pikepdf.Name.XObject
            form_xobj.Subtype = pikepdf.Name.Form
            form_xobj.FormType = 1
            form_xobj.BBox = list(stamp_page.MediaBox)
            form_xobj.Matrix = [1, 0, 0, 1, 0, 0]
            
            # Resources
            if "/Resources" in stamp_page:
                new_res = pikepdf.Dictionary()
                for k, v in stamp_page.Resources.items():
                    try:
                        new_res[k] = target_pdf.copy_foreign(v)
                    except:
                        new_res[k] = v
                form_xobj.Resources = new_res
            else:
                form_xobj.Resources = pikepdf.Dictionary()
            
            # Additional Metadata for Management
            stamp_id = str(uuid.uuid4())
            xobj_name = f"KPaperFlux_{stamp_id}".replace("-", "") 
            
            # Add to Page Resources
            if "/Resources" not in first_page:
                first_page.Resources = pikepdf.Dictionary()
            if "/XObject" not in first_page.Resources:
                first_page.Resources.XObject = pikepdf.Dictionary()
            
            first_page.Resources.XObject[f"/{xobj_name}"] = form_xobj
            
            # Add metadata to XObject for text retrieval
            form_xobj.KPaperFlux_Text = text
            form_xobj.KPaperFlux_ID = stamp_id
            
            # Append 'Do' command to content stream (as separate stream object)
            do_cmd_stream = target_pdf.make_stream(f"/{xobj_name} Do".encode())
            if "/Contents" not in first_page:
                first_page.Contents = do_cmd_stream
            else:
                if isinstance(first_page.Contents, pikepdf.Array):
                    first_page.Contents.append(do_cmd_stream)
                else:
                    first_page.Contents = pikepdf.Array([first_page.Contents, do_cmd_stream])
            
            target_pdf.save(output_path)
            
        except Exception as e:
            print(f"Stamping error: {e}")
            raise

    def get_stamps(self, file_path: str) -> List[Dict]:
        """
        Returns a list of existing KPaperFlux stamps (XObjects).
        """
        stamps = []
        try:
            pdf = pikepdf.Pdf.open(file_path)
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
            print(f"Error getting stamps: {e}")
            raise

    def has_stamp(self, file_path: str) -> bool:
        return len(self.get_stamps(file_path)) > 0

    def remove_stamp(self, file_path: str, stamp_id: Optional[str] = None) -> bool:
        """
        Removes KPaperFlux stamps (XObjects and Do commands).
        """
        try:
            pdf = pikepdf.Pdf.open(file_path, allow_overwriting_input=True)
            removed = False
            
            # Iterate pages
            for page in pdf.pages:
                if "/Resources" not in page or "/XObject" not in page.Resources:
                    continue
                
                xobjects = page.Resources.XObject
                names_to_remove = []
                
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
                            names_to_remove.append(name)
                
                if not names_to_remove:
                    continue
                    
                # 2. Cleanup Content Stream
                if "/Contents" in page:
                    contents = page.Contents
                    
                    if isinstance(contents, pikepdf.Array):
                        new_contents = []
                        for stream in contents:
                            data = stream.read_bytes()
                            is_stamp_stream = False
                            # Check if matches any removed name
                            for n in names_to_remove:
                                # name is usually "/KPaperFlux..." (key) or "KPaperFlux..." depending on pikepdf version?
                                # items() returns (key, val). Key is String in pikepdf usually? NO, keys are Names usually e.g. /Foo.
                                # But let's handle string match.
                                clean_name = str(n).replace("/", "")
                                search_term = f"/{clean_name} Do".encode()
                                if search_term in data:
                                    is_stamp_stream = True
                                    break
                            
                            if not is_stamp_stream:
                                new_contents.append(stream)
                        
                        page.Contents = pikepdf.Array(new_contents)
                    
                    else:
                        # Single stream. Parse.
                        commands = pikepdf.parse_content_stream(page)
                        new_commands = []
                        for operands, operator in commands:
                            if operator == "Do":
                                if len(operands) > 0:
                                    op_name = operands[0] 
                                    match = False
                                    for n in names_to_remove:
                                        # Compare pikepdf.Name
                                        if op_name == pikepdf.Name(str(n)):
                                            match = True
                                            break
                                    if match:
                                        continue
                            new_commands.append((operands, operator))
                        
                        page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(new_commands))

                # 3. Remove from Resources (After scan)
                for name in names_to_remove:
                    del xobjects[name]
                
                removed = True

            if removed:
                pdf.save(file_path)
                return True
                
            return False
            
        except Exception as e:
            print(f"Error removing stamp: {e}")
            raise
