import os
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, 
    Frame, PageTemplate, BaseDocTemplate, NextPageTemplate
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

from core.models.semantic import SemanticExtraction, AddressInfo

logger = logging.getLogger("KPaperFlux.PdfRenderer")

class ProfessionalPdfRenderer:
    """
    Generates high-quality DIN 5008 compliant PDFs using ReportLab.
    Supports multi-page documents with proper headers and footers.
    """
    
    def __init__(self, output_path: str, locale: str = "de"):
        self.path = output_path
        self.locale = locale.split("_")[0].lower()
        self.unit_codes = self._load_unit_codes()
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Initializes internal ParagraphStyle objects."""
        self.styles.add(ParagraphStyle(
            name='NormalSmall',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10
        ))
        self.styles.add(ParagraphStyle(
            name='TableHeading',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold'
        ))
        self.styles.add(ParagraphStyle(
            name='TableCell',
            parent=self.styles['Normal'],
            fontSize=9,
            leading=11
        ))
        self.styles.add(ParagraphStyle(
            name='Statement',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=14,
            leftIndent=10*mm,
            spaceBefore=5,
            spaceAfter=5
        ))
        self.styles.add(ParagraphStyle(
            name='LegalHeading',
            parent=self.styles['Normal'],
            fontSize=11,
            fontName='Helvetica-Bold',
            spaceBefore=10,
            spaceAfter=5
        ))

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
        # Page 1 Frame: Starts lower to leave room for address/meta
        frame_first = Frame(20*mm, 35*mm, 170*mm, 230*mm, id='f1')
        # Follow-up Frame: Larger, starts higher
        frame_others = Frame(20*mm, 35*mm, 170*mm, 245*mm, id='f2')
        
        # Add page templates
        doc.addPageTemplates([
            PageTemplate(id='first', frames=frame_first, onPage=lambda c, d: self._draw_static_elements(c, d, data, is_first=True)),
            PageTemplate(id='others', frames=frame_others, onPage=lambda c, d: self._draw_static_elements(c, d, data, is_first=False))
        ])

        story = []
        
        # 1. CRITICAL: Tell the engine to switch template after the current page
        story.append(NextPageTemplate('others'))
        
        # 2. Spacer to jump over the static header area on page 1
        story.append(Spacer(1, 128*mm))
        
        # 3. Dynamic Content Selection
        # If we have a Certificate/Legal Body, render it first
        story.extend(self._create_legal_body_story(data))
        
        # If we have line items (Invoices etc), render them
        story.extend(self._create_line_items_story(data))
        
        # 4. Totals (Financial only)
        story.append(Spacer(1, 5*mm))
        story.extend(self._create_totals_story(data))
        
        # Build document
        doc.build(story)

    def _draw_static_elements(self, canvas, doc, data, is_first: bool):
        """Callback to draw background elements on every page."""
        canvas.saveState()
        
        # -- 1. CORPORATE HEADER (All pages) --
        sender = data.meta_header.sender if data.meta_header else None
        if sender:
            # Top Right Logo Area
            canvas.setFont("Helvetica-Bold", 12)
            canvas.drawRightString(190*mm, 297*mm - 20*mm, (sender.company or sender.name or "").upper())
            
            canvas.setFont("Helvetica", 9)
            y = 297*mm - 25*mm
            street_full = f"{sender.street or ''} {sender.house_number or ''}".strip()
            if street_full:
                canvas.drawRightString(190*mm, y, street_full)
                y -= 4*mm
            if sender.city:
                canvas.drawRightString(190*mm, y, f"{sender.zip_code or ''} {sender.city}")
        
        # -- 2. FIRST PAGE SPECIFICS (Address/Meta) --
        if is_first:
            # Sender Reference Line
            if sender:
                canvas.setFont("Helvetica", 7)
                canvas.setFillGray(0.3)
                street_full = f"{sender.street or ''} {sender.house_number or ''}".strip()
                ref_line = f"{sender.company or sender.name} \u2022 {street_full} \u2022 {sender.zip_code} {sender.city}"
                canvas.drawString(20*mm, 297*mm - 42*mm, ref_line)
                canvas.line(20*mm, 297*mm - 43*mm, 100*mm, 297*mm - 43*mm)

            # Recipient Address
            recipient = data.meta_header.recipient if data.meta_header else None
            if recipient:
                canvas.setFont("Helvetica", 11)
                canvas.setFillGray(0)
                y = 297*mm - 50*mm
                addr_lines = []
                if recipient.company: addr_lines.append(recipient.company)
                if recipient.name: addr_lines.append(recipient.name)
                s_full = f"{recipient.street or ''} {recipient.house_number or ''}".strip()
                if s_full: addr_lines.append(s_full)
                if recipient.city: addr_lines.append(f"{recipient.zip_code or ''} {recipient.city}")
                if recipient.country and recipient.country.upper() != "DE": addr_lines.append(recipient.country.upper())
                
                for line in addr_lines:
                    canvas.drawString(20*mm, y, line)
                    y -= 5*mm

            # Meta Info Box (Right)
            self._draw_meta_info_box(canvas, data)

            # Main Title
            self._draw_main_title_text(canvas, data)

        # -- 3. FOOTER (All pages) --
        if sender:
            canvas.setFont("Helvetica", 8)
            canvas.setFillGray(0.4)
            canvas.line(20*mm, 30*mm, 190*mm, 30*mm)
            
            y_f = 25*mm
            # Col 1
            canvas.drawString(20*mm, y_f, sender.company or sender.name or "")
            street_f = f"{sender.street or ''} {sender.house_number or ''}".strip()
            canvas.drawString(20*mm, y_f - 4*mm, street_f)
            canvas.drawString(20*mm, y_f - 8*mm, f"{sender.zip_code or ''} {sender.city or ''}")
            
            # Col 2
            if sender.iban:
                canvas.drawString(80*mm, y_f, f"Bank: {sender.bank_name or 'Bank'}")
                canvas.drawString(80*mm, y_f - 4*mm, f"IBAN: {sender.iban}")
                if sender.bic: canvas.drawString(80*mm, y_f - 8*mm, f"BIC: {sender.bic}")

            # Page Number
            canvas.drawRightString(190*mm, 15*mm, f"Seite {doc.page}")

        canvas.restoreState()

    def _draw_meta_info_box(self, canvas, data: SemanticExtraction):
        """Draws the right-aligned meta data block."""
        fb = data.bodies.get("finance_body")
        y = 297*mm - 85*mm
        
        def draw_kv(label, val, y_pos):
            if val is None: return y_pos
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawRightString(160*mm, y_pos, f"{label}:")
            canvas.setFont("Helvetica", 10)
            canvas.drawString(165*mm, y_pos, str(val))
            return y_pos - 5*mm
        
        inv_date = getattr(fb, "invoice_date", None) if fb else None
        if not inv_date and data.meta_header: inv_date = data.meta_header.doc_date
        if inv_date:
            from core.utils.formatting import format_date
            y = draw_kv("Datum", format_date(inv_date, locale=self.locale), y)
            
        inv_num = getattr(fb, "invoice_number", None) if fb else None
        if not inv_num and data.meta_header: inv_num = data.meta_header.doc_number
        if inv_num: y = draw_kv("Beleg-Nr", inv_num, y)

        if fb:
            if hasattr(fb, 'order_number') and fb.order_number:
                y = draw_kv("Auftrag-Nr", str(fb.order_number), y)
            if hasattr(fb, 'customer_id') and fb.customer_id:
                y = draw_kv("Kunden-Nr", str(fb.customer_id), y)

    def _draw_main_title_text(self, canvas, data: SemanticExtraction):
        """Draws the Document Type title."""
        canvas.setFont("Helvetica-Bold", 18)
        mapping = {
            "INVOICE": "Rechnung", "ORDER_CONFIRMATION": "Auftragsbest\u00e4tigung",
            "DELIVERY_NOTE": "Lieferschein", "RECEIPT": "Quittung", "CONTRACT": "Vertrag",
            "CERTIFICATE": "Zertifikat", "LETTER": "Schreiben"
        }
        tags = [mapping.get(t.upper(), t.capitalize()) for t in (data.type_tags or [])]
        title = " / ".join(list(dict.fromkeys(tags))) or "Dokument"
        canvas.drawString(20*mm, 297*mm - 130*mm, title.upper())
        
        fb = data.bodies.get("finance_body")
        if fb and hasattr(fb, 'order_date') and fb.order_date:
            from core.utils.formatting import format_date
            canvas.setFont("Helvetica", 9)
            label = "Ihre Bestellung vom" if self.locale == "de" else "Your order from"
            canvas.drawString(20*mm, 297*mm - 135*mm, f"{label} {format_date(fb.order_date, locale=self.locale)}")

    def _create_line_items_story(self, data: SemanticExtraction) -> List[Any]:
        """Creates the Table flowable for line items."""
        fb = data.bodies.get("finance_body")
        items = getattr(fb, "line_items", []) if fb else []
        if not items:
            # We only show this message if it's purely a financial document without items
            # If it's a certificate, we just skip the table silently
            if "INVOICE" in [t.upper() for t in (data.type_tags or [])]:
                return [Paragraph("Keine Positionen aufgef\u00fchrt.", self.styles['Normal'])]
            return []

        table_data = [[
            Paragraph("Pos", self.styles['TableHeading']),
            Paragraph("Menge", self.styles['TableHeading']),
            Paragraph("Einheit", self.styles['TableHeading']),
            Paragraph("Beschreibung", self.styles['TableHeading']),
            Paragraph("E-Preis", self.styles['TableHeading']),
            Paragraph("Gesamt", self.styles['TableHeading'])
        ]]
        
        from core.utils.formatting import format_currency
        for i, item in enumerate(items):
            def gv(k): return getattr(item, k, None) if not isinstance(item, dict) else item.get(k)
            unit_r = gv("unit") or "Stk"
            row = [
                str(gv("pos") or i+1),
                str(gv("quantity") or "1"),
                self.unit_codes.get(str(unit_r).upper(), unit_r),
                Paragraph(str(gv("description") or "---"), self.styles['TableCell']),
                format_currency(gv('unit_price') or 0, locale=self.locale),
                format_currency(gv('total_price') or 0, locale=self.locale)
            ]
            table_data.append(row)

        # -- Calculate Dynamic Column Widths --
        total_available = 170*mm
        # Measured indices: 0: Pos, 1: Menge, 2: Einheit, 4: E-Preis, 5: Gesamt
        measured_widths = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        
        # Helper to get text from Cell (could be string or Paragraph)
        def get_text(cell):
            if isinstance(cell, Paragraph): return cell.text
            return str(cell)

        for row in table_data:
            for i in [0, 1, 2, 4, 5]:
                # Measure text width in Helvetica 9pt (our table font)
                w = stringWidth(get_text(row[i]), "Helvetica", 9) + 4*mm # + padding
                measured_widths[i] = max(measured_widths[i], w)

        # Enforce minimums for columns
        measured_widths[0] = max(10*mm, measured_widths[0]) # Pos
        measured_widths[1] = max(15*mm, measured_widths[1]) # Menge
        measured_widths[2] = max(15*mm, measured_widths[2]) # Einheit
        measured_widths[4] = max(22*mm, measured_widths[4]) # E-Preis
        measured_widths[5] = max(23*mm, measured_widths[5]) # Gesamt
        
        # Description (index 3) takes the rest
        used_width = sum(measured_widths)
        measured_widths[3] = max(40*mm, total_available - used_width)

        table = Table(table_data, colWidths=measured_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEBELOW', (0,0), (-1,0), 1.5, colors.black),
            ('LINEBELOW', (0,1), (-1,-1), 0.5, colors.grey),
            ('ALIGN', (4,0), (-1,-1), 'RIGHT'),
        ]))
        return [table]

    def _create_totals_story(self, data: SemanticExtraction) -> List[Any]:
        """Creates a table-based summary for totals."""
        fb = data.bodies.get("finance_body")
        if not fb: return []
        ms = getattr(fb, "monetary_summation", None)
        if not ms: return []
        
        from core.utils.formatting import format_currency
        def gv(k): return getattr(ms, k, None) if not isinstance(ms, dict) else ms.get(k)
        
        t_rows = []
        mapping = [
            ("Summe Positionen", "line_total_amount", False),
            ("Netto Summe", "tax_basis_total_amount", False),
            ("Umsatzsteuer", "tax_total_amount", False),
            ("RECHNUNGSBETRAG", "grand_total_amount", True)
        ]
        
        for label, key, bold in mapping:
            val = gv(key)
            if val is not None:
                t_rows.append([label, format_currency(val, currency="EUR", locale=self.locale)])

        if not t_rows: return []
        
        table = Table(t_rows, colWidths=[120*mm, 50*mm])
        # Style needs to right align values
        t_style = [
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]
        
        # Bold the last entry (Grand Total)
        if t_rows:
            last = len(t_rows) - 1
            t_style.append(('FONTNAME', (0, last), (1, last), 'Helvetica-Bold'))
            t_style.append(('LINEABOVE', (0, last), (1, last), 1, colors.black))
            t_style.append(('LINEBELOW', (0, last), (1, last), 2, colors.black))
            
        table.setStyle(TableStyle(t_style))
        return [table]

    def _create_legal_body_story(self, data: SemanticExtraction) -> List[Any]:
        """Renders statements and compliance info (e.g. for Certificates)."""
        lb = data.bodies.get("legal_body")
        if not lb: return []
        
        story = []
        
        # Show Certificate ID / Subject if available
        def gv(k): return getattr(lb, k, None) if not isinstance(lb, dict) else lb.get(k)
        
        doc_id = gv("certificate_id")
        if doc_id:
            story.append(Paragraph(f"Zertifikat-ID: {doc_id}", self.styles['LegalHeading']))
        
        subject = gv("subject_reference")
        if subject:
             story.append(Paragraph(f"Referenz: {subject}", self.styles['Normal']))

        # Main Statements
        statements = gv("statements") or []
        if statements:
            story.append(Paragraph("Aussagen & Erkl\u00e4rungen:", self.styles['LegalHeading']))
            for s in statements:
                story.append(Paragraph(f"\u2022 {s}", self.styles['Statement']))

        # Standards
        standards = gv("compliance_standards") or []
        if standards:
            story.append(Paragraph("Eingehaltene Normen / Standards:", self.styles['LegalHeading']))
            std_text = ", ".join(standards)
            story.append(Paragraph(std_text, self.styles['Statement']))
            
        story.append(Spacer(1, 10*mm))
        return story
