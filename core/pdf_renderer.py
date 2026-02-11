"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/pdf_renderer.py
Version:        2.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Enhanced DIN 5008 compliant PDF renderer. Supports corporate
                branding (logos, colors), dynamic table layouts, and font 
                variety for realistic demo document generation.
------------------------------------------------------------------------------
"""

import os
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, 
    Frame, PageTemplate, BaseDocTemplate, NextPageTemplate, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

from core.models.semantic import SemanticExtraction, AddressInfo

logger = logging.getLogger("KPaperFlux.PdfRenderer")

class ProfessionalPdfRenderer:
    """
    Generates high-quality DIN 5008 compliant PDFs using ReportLab.
    Supports multi-page documents with proper headers and footers.
    Includes support for corporate branding and style variety.
    """
    
    def __init__(self, output_path: str, locale: str = "de"):
        self.path = output_path
        self.locale = locale.split("_")[0].lower()
        self.unit_codes = self._load_unit_codes()
        self.styles = getSampleStyleSheet()
        
        # Style Customization (can be overridden)
        self.primary_color = colors.black
        self.font_family = "Helvetica"
        self.font_family_bold = "Helvetica-Bold"
        self.logo_path = None
        self.table_columns = ["pos", "quantity", "unit", "description", "unit_price", "total_price"]
        
        self._setup_custom_styles()

    def set_style(self, primary_color: Any = colors.black, font: str = "Helvetica", logo: str = None, columns: List[str] = None):
        """Overrides default style settings."""
        self.primary_color = primary_color
        self.font_family = font
        self.font_family_bold = f"{font}-Bold" if font != "Times-Roman" else "Times-Bold"
        if font == "Times-Roman": self.font_family_bold = "Times-Bold"
        elif font == "Courier": self.font_family_bold = "Courier-Bold"
        
        self.logo_path = logo
        if columns: self.table_columns = columns
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Initializes internal ParagraphStyle objects."""
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
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except:
                    pass
        return {}

    def render_document(self, data: SemanticExtraction):
        """Main entry point to render the semantic data using Platypus."""
        doc = BaseDocTemplate(self.path, pagesize=A4)
        
        # Define frames
        frame_first = Frame(20*mm, 35*mm, 170*mm, 230*mm, id='f1')
        frame_others = Frame(20*mm, 35*mm, 170*mm, 245*mm, id='f2')
        
        doc.addPageTemplates([
            PageTemplate(id='first', frames=frame_first, onPage=lambda c, d: self._draw_static_elements(c, d, data, is_first=True)),
            PageTemplate(id='others', frames=frame_others, onPage=lambda c, d: self._draw_static_elements(c, d, data, is_first=False))
        ])

        story = []
        story.append(NextPageTemplate('others'))
        story.append(Spacer(1, 128*mm)) # Jump static header area on page 1
        
        story.extend(self._create_legal_body_story(data))
        story.extend(self._create_line_items_story(data))
        story.append(Spacer(1, 5*mm))
        story.extend(self._create_totals_story(data))
        
        doc.build(story)

    def _draw_static_elements(self, canvas, doc, data, is_first: bool):
        canvas.saveState()
        sender = data.meta_header.sender if data.meta_header else None
        
        # -- 1. CORPORATE HEADER (All pages) --
        if sender:
            # Top Right Area (Logo / Brand)
            y = 297*mm - 20*mm
            if self.logo_path and os.path.exists(self.logo_path):
                canvas.drawImage(self.logo_path, 160*mm, y-15*mm, width=30*mm, preserveAspectRatio=True, mask='auto')
                y -= 25*mm
            
            # Company Name
            canvas.setFillColor(self.primary_color)
            if sender.company:
                canvas.setFont(self.font_family_bold, 12)
                canvas.drawRightString(190*mm, y, sender.company.upper())
                y -= 5*mm
                if sender.name and sender.name != sender.company:
                    canvas.setFont(self.font_family, 10)
                    canvas.drawRightString(190*mm, y, sender.name)
                    y -= 5*mm
            elif sender.name:
                canvas.setFont(self.font_family_bold, 12)
                canvas.drawRightString(190*mm, y, sender.name.upper())
                y -= 5*mm
            
            # Address info
            canvas.setFillColor(colors.black)
            canvas.setFont(self.font_family, 9)
            y -= 2*mm
            street_full = f"{sender.street or ''} {sender.house_number or ''}".strip()
            if street_full:
                canvas.drawRightString(190*mm, y, street_full)
                y -= 4*mm
            if sender.city:
                canvas.drawRightString(190*mm, y, f"{sender.zip_code or ''} {sender.city}")

        # -- 2. FIRST PAGE SPECIFICS --
        if is_first:
            if sender:
                canvas.setFont(self.font_family, 7)
                canvas.setFillGray(0.3)
                street_f = f"{sender.street or ''} {sender.house_number or ''}".strip()
                ref_line = f"{sender.company or sender.name} \u2022 {street_f} \u2022 {sender.zip_code} {sender.city}"
                canvas.drawString(20*mm, 297*mm - 42*mm, ref_line)
                canvas.setStrokeColor(self.primary_color)
                canvas.line(20*mm, 297*mm - 43*mm, 100*mm, 297*mm - 43*mm)

            recipient = data.meta_header.recipient if data.meta_header else None
            if recipient:
                canvas.setFont(self.font_family, 11)
                canvas.setFillGray(0)
                y = 297*mm - 50*mm
                addr_lines = []
                if recipient.company: addr_lines.append(recipient.company)
                if recipient.name and recipient.name != recipient.company: addr_lines.append(recipient.name)
                s_full = f"{recipient.street or ''} {recipient.house_number or ''}".strip()
                if s_full: addr_lines.append(s_full)
                if recipient.city: addr_lines.append(f"{recipient.zip_code or ''} {recipient.city}")
                if recipient.country and recipient.country.upper() != "DE": addr_lines.append(recipient.country.upper())
                
                for line in addr_lines:
                    canvas.drawString(20*mm, y, line)
                    y -= 5*mm

            self._draw_meta_info_box(canvas, data)
            self._draw_main_title_text(canvas, data)

        # -- 3. FOOTER (All pages) --
        if sender:
            canvas.setFont(self.font_family, 8)
            canvas.setFillGray(0.4)
            canvas.setStrokeColor(self.primary_color)
            canvas.line(20*mm, 30*mm, 190*mm, 30*mm)
            
            y_f = 25*mm
            # Col 1: Identity
            if sender.company:
                canvas.drawString(20*mm, y_f, sender.company)
                y_f -= 4*mm
                if sender.name and sender.name != sender.company:
                    canvas.drawString(20*mm, y_f, sender.name)
                    y_f -= 4*mm
            elif sender.name:
                canvas.drawString(20*mm, y_f, sender.name)
                y_f -= 4*mm
            street_f = f"{sender.street or ''} {sender.house_number or ''}".strip()
            if street_f:
                canvas.drawString(20*mm, y_f, street_f)
                y_f -= 4*mm
            canvas.drawString(20*mm, y_f, f"{sender.zip_code or ''} {sender.city or ''}")
            
            # Col 2 & 3: Bank Accounts
            fb = data.bodies.get("finance_body")
            accounts = getattr(fb, "payment_accounts", []) if fb else []
            if not accounts and sender.iban: accounts = [sender]
            bank_x = 80*mm
            for acc in accounts[:3]:
                y_f_acc = 25*mm
                canvas.drawString(bank_x, y_f_acc, f"Bank: {acc.bank_name or 'Bank'}")
                if acc.iban: canvas.drawString(bank_x, y_f_acc - 4*mm, f"IBAN: {acc.iban}")
                if acc.bic: canvas.drawString(bank_x, y_f_acc - 8*mm, f"BIC: {acc.bic}")
                bank_x += 45*mm

            canvas.drawRightString(190*mm, 15*mm, f"Seite {doc.page}")

        canvas.restoreState()

    def _draw_meta_info_box(self, canvas, data: SemanticExtraction):
        fb = data.bodies.get("finance_body")
        y = 297*mm - 85*mm
        def draw_kv(label, val, y_pos):
            if not val: return y_pos
            canvas.setFont(self.font_family_bold, 10)
            canvas.drawRightString(160*mm, y_pos, f"{label}:")
            canvas.setFont(self.font_family, 10)
            canvas.drawString(165*mm, y_pos, str(val))
            return y_pos - 5*mm
        
        inv_date = getattr(fb, "invoice_date", None) or (data.meta_header.doc_date if data.meta_header else None)
        if inv_date:
            from core.utils.formatting import format_date
            label = "Date" if self.locale == "en" else "Datum"
            y = draw_kv(label, format_date(inv_date, locale=self.locale), y)
            
        inv_num = getattr(fb, "invoice_number", None) or (data.meta_header.doc_number if data.meta_header else None)
        if inv_num:
            label = "Inv-No" if self.locale == "en" else "Beleg-Nr"
            y = draw_kv(label, inv_num, y)

        if fb:
            if hasattr(fb, 'customer_id') and fb.customer_id:
                label = "Customer" if self.locale == "en" else "Kunden-Nr"
                y = draw_kv(label, str(fb.customer_id), y)

    def _draw_main_title_text(self, canvas, data: SemanticExtraction):
        canvas.setFont(self.font_family_bold, 18)
        canvas.setFillColor(self.primary_color)
        mapping = {
            "INVOICE": "Rechnung", "ORDER_CONFIRMATION": "Auftragsbest\u00e4tigung",
            "DELIVERY_NOTE": "Lieferschein", "RECEIPT": "Quittung", "CONTRACT": "Vertrag"
        }
        if self.locale == "en":
             mapping = {"INVOICE": "Invoice", "RECEIPT": "Receipt", "CONTRACT": "Contract"}
        
        tags = [mapping.get(t.upper(), t.capitalize()) for t in (data.type_tags or [])]
        title = " / ".join(list(dict.fromkeys(tags))) or "Document"
        canvas.drawString(20*mm, 297*mm - 130*mm, title.upper())

    def _create_line_items_story(self, data: SemanticExtraction) -> List[Any]:
        fb = data.bodies.get("finance_body")
        items = getattr(fb, "line_items", []) if fb else []
        if not items: return []

        # Map internal column keys to display labels
        labels = {
            "pos": "Pos", "quantity": "Menge" if self.locale == "de" else "Qty",
            "unit": "Einh" if self.locale == "de" else "Unit",
            "description": "Beschreibung" if self.locale == "de" else "Description",
            "unit_price": "E-Preis" if self.locale == "de" else "Price",
            "total_price": "Gesamt" if self.locale == "de" else "Total"
        }
        
        header_row = [Paragraph(labels.get(col, col), self.styles['TableHeading']) for col in self.table_columns]
        table_data = [header_row]
        
        from core.utils.formatting import format_currency
        for i, item in enumerate(items):
            row = []
            for col in self.table_columns:
                val = getattr(item, col, None) if not isinstance(item, dict) else item.get(col)
                if col == "pos" and not val: val = str(i+1)
                elif col == "unit": val = self.unit_codes.get(str(val).upper(), val) or "Stk"
                elif col in ["unit_price", "total_price"]: val = format_currency(val or 0, locale=self.locale)
                elif col == "description": val = Paragraph(str(val or "---"), self.styles['TableCell'])
                row.append(str(val if val is not None else ""))
            table_data.append(row)

        total_width = 170*mm
        # Simplified column width logic (can be refined)
        col_count = len(self.table_columns)
        widths = []
        for col in self.table_columns:
            if col in ["pos", "quantity", "unit"]: widths.append(12*mm)
            elif col in ["unit_price", "total_price"]: widths.append(25*mm)
            else: widths.append(0) # placeholder for description
            
        desc_idx = self.table_columns.index("description") if "description" in self.table_columns else -1
        if desc_idx != -1:
             widths[desc_idx] = total_width - sum(widths)
        else:
            # Equalize if no description
            widths = [total_width/col_count] * col_count

        table = Table(table_data, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), self.font_family),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LINEBELOW', (0,0), (-1,0), 1.5, self.primary_color),
            ('LINEBELOW', (0,1), (-1,-1), 0.5, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        return [table]

    def _create_totals_story(self, data: SemanticExtraction) -> List[Any]:
        fb = data.bodies.get("finance_body")
        ms = getattr(fb, "monetary_summation", None) if fb else None
        if not ms: return []
        
        from core.utils.formatting import format_currency
        def gv(k): return getattr(ms, k, None) if not isinstance(ms, dict) else ms.get(k)
        
        labels_map = {
            "line_total_amount": "Summe Netto" if self.locale=="de" else "Net Total",
            "tax_total_amount": "Umsatzsteuer" if self.locale=="de" else "Tax",
            "grand_total_amount": "GESAMTBETRAG" if self.locale=="de" else "GRAND TOTAL"
        }
        
        t_rows = []
        for key in ["line_total_amount", "tax_total_amount", "grand_total_amount"]:
            val = gv(key)
            if val: t_rows.append([labels_map[key], format_currency(val, locale=self.locale)])

        if not t_rows: return []
        table = Table(t_rows, colWidths=[120*mm, 50*mm])
        table.setStyle(TableStyle([
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('FONTNAME', (0,-1), (1,-1), self.font_family_bold),
            ('LINEABOVE', (0,-1), (1,-1), 1, self.primary_color),
        ]))
        return [table]

    def _create_legal_body_story(self, data: SemanticExtraction) -> List[Any]:
        lb = data.bodies.get("legal_body")
        if not lb: return []
        story = []
        def gv(k): return getattr(lb, k, None) if not isinstance(lb, dict) else lb.get(k)
        
        doc_id = gv("certificate_id")
        if doc_id: story.append(Paragraph(f"Ref: {doc_id}", self.styles['LegalHeading']))
        statements = gv("statements") or []
        for s in statements: story.append(Paragraph(f"\u2022 {s}", self.styles['Statement']))
        return story
