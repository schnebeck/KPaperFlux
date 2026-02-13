"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/pdf_renderer.py
Version:        2.3.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Highly creative and diverse PDF renderer. Supports multiple
                layout concepts (Classic, Modern, Minimal, Industrial) with
                varying column orders, colors, and line styles to create
                truly unique demo documents.
------------------------------------------------------------------------------
"""

import os
import logging
import random
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, 
    Frame, PageTemplate, BaseDocTemplate, NextPageTemplate, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

from core.models.semantic import SemanticExtraction, AddressInfo

logger = logging.getLogger("KPaperFlux.PdfRenderer")

class ProfessionalPdfRenderer:
    """
    Generates extremely diverse DIN 5008 compliant PDFs using ReportLab.
    Supports multiple design concepts and structural variations.
    """
    
    def __init__(self, output_path: str, locale: str = "de"):
        self.path = output_path
        self.locale = locale.split("_")[0].lower()
        self.unit_codes = self._load_unit_codes()
        self.styles = getSampleStyleSheet()
        
        # Design State
        self.primary_color = colors.black
        self.font_family = "Helvetica"
        self.font_family_bold = "Helvetica-Bold"
        self.logo_path = None
        self.table_columns = ["pos", "quantity", "unit", "description", "unit_price", "total_price"]
        self.concept = "CLASSIC" # CLASSIC, MODERN, MINIMAL, INDUSTRIAL
        self.line_style = "SOLID" # SOLID, DASHED, THICK
        
        self._setup_custom_styles()

    def set_style(self, concept: str = "CLASSIC", color: Any = colors.black, font: str = "Helvetica", 
                  logo: str = None, columns: List[str] = None, line_style: str = "SOLID"):
        self.concept = concept.upper()
        self.primary_color = color
        self.font_family = font
        self.font_family_bold = f"{font}-Bold" if font not in ["Times-Roman", "Courier"] else f"{font.split('-')[0]}-Bold"
        if font == "Times-Roman": self.font_family_bold = "Times-Bold"
        elif font == "Courier": self.font_family_bold = "Courier-Bold"
        
        self.logo_path = logo
        self.line_style = line_style
        if columns: self.table_columns = columns
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        style_defs = [
            ('NormalSmall', 'Normal', 8, 10, self.font_family),
            ('TableHeading', 'Normal', 9, 11, self.font_family_bold),
            ('TableCell', 'Normal', 9, 11, self.font_family),
            ('Statement', 'Normal', 10, 14, self.font_family),
            ('LegalHeading', 'Normal', 11, 13, self.font_family_bold)
        ]
        for name, parent, size, leading, font in style_defs:
            if name in self.styles:
                self.styles[name].fontName = font
                self.styles[name].fontSize = size
                self.styles[name].leading = leading
            else:
                self.styles.add(ParagraphStyle(name=name, parent=self.styles[parent], fontSize=size, leading=leading, fontName=font))

    def _load_unit_codes(self) -> dict:
        import json
        for loc in [self.locale, "en"]:
            path = os.path.join("resources", "l10n", loc, "units.json")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: return json.load(f)
                except: pass
        return {}

    def render_document(self, data: SemanticExtraction):
        doc = BaseDocTemplate(self.path, pagesize=A4)
        frame_first = Frame(20*mm, 35*mm, 170*mm, 230*mm, id='f1')
        frame_others = Frame(20*mm, 35*mm, 170*mm, 245*mm, id='f2')
        
        doc.addPageTemplates([
            PageTemplate(id='first', frames=frame_first, onPage=lambda c, d: self._draw_static_elements(c, d, data, is_first=True)),
            PageTemplate(id='others', frames=frame_others, onPage=lambda c, d: self._draw_static_elements(c, d, data, is_first=False))
        ])

        story = [NextPageTemplate('others'), Spacer(1, 130*mm)]
        story.extend(self._create_legal_body_story(data))
        story.extend(self._create_line_items_story(data))
        story.append(Spacer(1, 10*mm))
        story.extend(self._create_totals_story(data))
        doc.build(story)

    def _draw_line(self, canvas, x1, y, x2, width=0.5):
        canvas.setStrokeColor(self.primary_color)
        canvas.setLineWidth(width)
        if self.line_style == "DASHED": canvas.setDash(3, 3)
        else: canvas.setDash()
        canvas.line(x1, y, x2, y)

    def _draw_static_elements(self, canvas, doc, data, is_first: bool):
        canvas.saveState()
        sender = data.meta_header.sender if data.meta_header else None
        
        # 1. HEADER LOGIC (CONCEPT DEPENDENT)
        if sender:
            if is_first:
                # 1. LOGO placement
                if self.logo_path and os.path.exists(self.logo_path):
                    try:
                        from PIL import Image as PILImage
                        with PILImage.open(self.logo_path) as img:
                            w, h = img.size
                            aspect = h / w
                            logo_w = 30*mm
                            logo_h = logo_w * aspect
                            if logo_h > 25*mm: # Max height 25mm
                                logo_h = 25*mm
                                logo_w = logo_h / aspect
                            logo_img = RLImage(self.logo_path, width=logo_w, height=logo_h, mask='auto')
                    except: logo_img = ""
                else: logo_img = ""

                # Sender Info as Paragraphs
                s_style = ParagraphStyle('HeaderSender', parent=self.styles['Normal'], fontSize=9, leading=11)
                c_style = ParagraphStyle('HeaderCompany', parent=self.styles['Normal'], fontSize=16, leading=19, fontName=self.font_family_bold, textColor=self.primary_color)
                
                s_parts = []
                if sender.company: s_parts.append(Paragraph(sender.company.upper(), c_style))
                addr = []
                if sender.street: addr.append(f"{sender.street} {sender.house_number or ''}".strip())
                if sender.zip_code or sender.city: addr.append(f"{sender.zip_code or ''} {sender.city or ''}".strip())
                if sender.country: addr.append(sender.country)
                s_parts.append(Paragraph("<br/>".join(addr), s_style))

                # Header Table
                # MODERN/INDUSTRIAL: [Logo, Text (Right)]
                # CLASSIC/MINIMAL: [Text (Left), Logo]
                is_left_logo = self.concept in ["MODERN", "INDUSTRIAL"]
                h_table_data = [[logo_img, s_parts]] if is_left_logo else [[s_parts, logo_img]]
                
                h_table = Table(h_table_data, colWidths=[95*mm, 95*mm])
                h_style = [
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ]
                if is_left_logo:
                    h_style.append(('ALIGN', (1,0), (1,0), 'RIGHT'))
                else:
                    h_style.append(('ALIGN', (0,0), (0,0), 'LEFT'))
                    h_style.append(('ALIGN', (1,0), (1,0), 'RIGHT'))

                h_table.setStyle(TableStyle(h_style))
                
                # Draw at the top
                w_h, h_h = h_table.wrap(190*mm, 100*mm)
                h_table.drawOn(canvas, 10*mm, 297*mm - 12*mm - h_h)
            else:
                # Page 2+ (Simplified Header)
                canvas.setFont(self.font_family, 8)
                canvas.setFillColor(colors.grey)
                doc_num = data.meta_header.doc_number if data.meta_header else ""
                header_text = f"{sender.company or sender.name} - {doc_num}"
                canvas.drawRightString(190*mm, 297*mm - 12*mm, header_text)

        # 2. SEPARATOR LINES (Varied Length)
        if is_first:
            line_y = 297*mm - 45*mm
            if self.concept == "MODERN": self._draw_line(canvas, 20*mm, line_y, 40*mm, width=2)
            elif self.concept == "CLASSIC": self._draw_line(canvas, 20*mm, line_y, 190*mm, width=0.5)
            elif self.concept == "INDUSTRIAL": self._draw_line(canvas, 10*mm, line_y, 200*mm, width=4) # Heavy line

            recipient = data.meta_header.recipient if data.meta_header else None
            if recipient:
                canvas.setFont(self.font_family, 10)
                y = 297*mm - 55*mm
                lines = []
                if recipient.company: lines.append(recipient.company)
                if recipient.name and recipient.name != recipient.company: lines.append(recipient.name)
                lines.append(f"{recipient.street or ''} {recipient.house_number or ''}")
                lines.append(f"{recipient.zip_code or ''} {recipient.city}")
                if recipient.country: lines.append(recipient.country.upper())
                for l in lines:
                    canvas.drawString(20*mm, y, l)
                    y -= 5*mm

            self._draw_meta_info_box(canvas, data)
            self._draw_main_title_text(canvas, data)

        # 3. FOOTER
        if sender:
            self._draw_line(canvas, 20*mm, 30*mm, 190*mm if self.concept != "MINIMAL" else 80*mm)
            canvas.setFont(self.font_family, 8)
            canvas.setFillGray(0.4)
            y_f = 25*mm
            
            # Col 1: Small Identity
            canvas.drawString(20*mm, y_f, (sender.company or sender.name or "")[:30])
            canvas.drawString(20*mm, y_f-4*mm, f"{sender.zip_code or ''} {sender.city or ''}")
            
            # Banking
            fb = data.bodies.get("finance_body")
            accounts = getattr(fb, "payment_accounts", []) or ([sender] if sender.iban else [])
            bank_x = 70*mm
            for acc in accounts[:2]:
                canvas.drawString(bank_x, 25*mm, f"{acc.bank_name or 'Bank'}")
                canvas.drawString(bank_x, 21*mm, f"IBAN {acc.iban or ''}")
                bank_x += 60*mm
            
            canvas.drawRightString(190*mm, 10*mm, f"PAGE {doc.page}" if self.locale=="en" else f"SEITE {doc.page}")

        canvas.restoreState()

    def _draw_meta_info_box(self, canvas, data: SemanticExtraction):
        fb = data.bodies.get("finance_body")
        # Layout variety for meta box
        x_label = 155*mm if self.concept != "INDUSTRIAL" else 60*mm
        x_val = 160*mm if self.concept != "INDUSTRIAL" else 100*mm
        y = 297*mm - 90*mm
        
        def draw_kv(l, v, y_pos):
            if not v: return y_pos
            canvas.setFont(self.font_family_bold, 9)
            canvas.drawRightString(x_label, y_pos, f"{l}:")
            canvas.setFont(self.font_family, 9)
            canvas.drawString(x_val, y_pos, str(v))
            return y_pos - 5*mm

        labels = {"dt": "Date" if self.locale=="en" else "Datum", "nr": "Number" if self.locale=="en" else "Beleg-Nr"}
        y = draw_kv(labels["dt"], getattr(fb, "invoice_date", None) or (data.meta_header.doc_date if data.meta_header else None), y)
        y = draw_kv(labels["nr"], getattr(fb, "invoice_number", None) or (data.meta_header.doc_number if data.meta_header else None), y)

    def _draw_main_title_text(self, canvas, data: SemanticExtraction):
        y_pos = 297*mm - 130*mm if self.concept not in ["INDUSTRIAL", "MINIMAL"] else 297*mm - 95*mm
        canvas.setFont(self.font_family_bold, 24 if self.concept=="MODERN" else 18)
        canvas.setFillColor(self.primary_color)
        
        # Multi-Type Tag Support
        tags = data.type_tags or ["INVOICE"]
        mapping = {"INVOICE": "INVOICE" if self.locale=="en" else "RECHNUNG",
                   "DELIVERY_NOTE": "DELIVERY NOTE" if self.locale=="en" else "LIEFERSCHEIN",
                   "ORDER_CONFIRMATION": "ORDER CONFIRMATION" if self.locale=="en" else "AUFTRAGSBESTÄTIGUNG"}
        
        title_parts = [mapping.get(t, t) for t in tags]
        title = " / ".join(title_parts)
        
        if self.concept == "INDUSTRIAL":
            canvas.drawRightString(190*mm, y_pos, title)
        elif self.concept == "MINIMAL":
            # Extra spacing for minimal
            canvas.drawCentredString(105*mm, y_pos - 10*mm, title)
        else:
            canvas.drawString(20*mm, y_pos, title)

    def _create_line_items_story(self, data: SemanticExtraction) -> List[Any]:
        fb = data.bodies.get("finance_body")
        items = getattr(fb, "line_items", []) if fb else []
        if not items: return []

        labels = {"pos": "#", "quantity": "Qty" if self.locale=="en" else "Menge", "unit": "Unit" if self.locale=="en" else "Einh", 
                  "description": "Description" if self.locale=="en" else "Beschreibung", 
                  "unit_price": "Price" if self.locale=="en" else "Preis", "total_price": "Total" if self.locale=="en" else "Summe"}
        
        header_row = [Paragraph(labels.get(col, col), self.styles['TableHeading']) for col in self.table_columns]
        table_data = [header_row]
        
        from core.utils.formatting import format_currency
        for i, item in enumerate(items):
            row = []
            for col in self.table_columns:
                v = getattr(item, col, None)
                if col == "pos" and not v: v = str(i+1)
                elif col == "unit": v = self.unit_codes.get(str(v).upper(), v) or "-"
                elif col in ["unit_price", "total_price"]: v = format_currency(v or 0, locale=self.locale)
                elif col == "description": v = Paragraph(str(v or "---"), self.styles['TableCell'])
                row.append(v if v is not None else "")
            table_data.append(row)

        total_width = 170*mm
        w_map = {"pos": 8*mm, "quantity": 15*mm, "unit": 12*mm, "unit_price": 25*mm, "total_price": 25*mm}
        widths = []
        for c in self.table_columns:
            if c != "description": widths.append(w_map.get(c, 15*mm))
            else: widths.append(0)
        
        if "description" in self.table_columns:
            di = self.table_columns.index("description")
            widths[di] = total_width - sum(widths)
        
        table = Table(table_data, colWidths=widths, repeatRows=1)
        
        # ELITE VARIETY: Variable Table Styling
        line_color = self.primary_color if self.concept != "MINIMAL" else colors.lightgrey
        t_style = [
            ('FONTNAME', (0,0), (-1,-1), self.font_family),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]

        # 1. Header Styling
        if self.concept == "MODERN":
            t_style.append(('BACKGROUND', (0,0), (-1,0), self.primary_color))
            t_style.append(('TEXTCOLOR', (0,0), (-1,0), colors.white))
        elif self.concept == "INDUSTRIAL":
            t_style.append(('BACKGROUND', (0,0), (-1,0), colors.lightgrey))
            t_style.append(('LINEBELOW', (0,0), (-1,0), 2, self.primary_color))
        else:
            t_style.append(('LINEBELOW', (0,0), (-1,0), 1, line_color))

        # 2. Zebra Stripes
        if self.concept in ["MODERN", "CLASSIC"] and len(table_data) > 3:
            for r in range(1, len(table_data)):
                if r % 2 == 0:
                    t_style.append(('BACKGROUND', (0, r), (-1, r), colors.whitesmoke))

        # 3. Grid Logic
        if self.concept == "INDUSTRIAL":
            t_style.append(('GRID', (0,0), (-1,-1), 0.5, colors.grey))
        elif self.concept == "MINIMAL":
            # No inner lines
            pass
        elif self.line_style == "DASHED":
            t_style.append(('LINEBELOW', (0,1), (-1,-2), 0.5, colors.lightgrey)) # Subtle lines
        else:
            t_style.append(('LINEBELOW', (0,1), (-1,-2), 0.2, colors.grey))

        table.setStyle(TableStyle(t_style))
        return [table]

    def _create_totals_story(self, data: SemanticExtraction) -> List[Any]:
        fb = data.bodies.get("finance_body")
        ms = getattr(fb, "monetary_summation", None) if fb else None
        if not ms: return []
        from core.utils.formatting import format_currency
        l_map = {"line_total_amount": "Net", "tax_total_amount": "Tax", "grand_total_amount": "TOTAL"}
        if self.locale=="de": l_map = {"line_total_amount": "Netto", "tax_total_amount": "MwSt", "grand_total_amount": "GESAMT"}
        
        t_rows = []
        for k in ["line_total_amount", "tax_total_amount", "grand_total_amount"]:
            v = getattr(ms, k, None)
            if v is not None: t_rows.append([l_map[k], format_currency(v, locale=self.locale)])

        if not t_rows: return []
        table = Table(t_rows, colWidths=[120*mm, 50*mm])
        table.setStyle(TableStyle([
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('FONTNAME', (0,-1), (1,-1), self.font_family_bold),
            ('FONTSIZE', (0,-1), (1,-1), 12 if self.concept=="MODERN" else 10),
            ('LINEABOVE', (0,-1), (1,-1), 1.5, self.primary_color),
        ]))
        return [table]

    def _create_legal_body_story(self, data: SemanticExtraction) -> List[Any]: return []
