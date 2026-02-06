
import os
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from typing import Optional, List, Any

from core.models.semantic import SemanticExtraction, AddressInfo

logger = logging.getLogger("KPaperFlux.PdfRenderer")

class ProfessionalPdfRenderer:
    """
    Generates high-quality DIN 5008 compliant PDFs using ReportLab.
    """
    
    def __init__(self, output_path: str, locale: str = "de"):
        self.path = output_path
        self.c = canvas.Canvas(output_path, pagesize=A4)
        self.width, self.height = A4
        self.locale = locale.split("_")[0].lower()
        self.unit_codes = self._load_unit_codes()

    def _load_unit_codes(self) -> dict:
        import json
        # Try current locale, then fallback to 'en'
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
        """Main entry point to render the semantic data."""
        self._draw_header(data)
        self._draw_address_block(data)
        self._draw_meta_info(data)
        self._draw_main_title(data)
        
        # Position table starts after title
        table_y = self._draw_line_items(data, start_y=160*mm)
        
        self._draw_totals(data, table_y)
        self._draw_footer(data)
        
        self.c.save()

    def _draw_header(self, data: SemanticExtraction):
        """Draws the sender line and bank info top-right."""
        sender = data.meta_header.sender if data.meta_header else None
        if not sender: return

        # Sender Small Line (above address window - optional but professional)
        self.c.setFont("Helvetica", 8)
        self.c.setFillGray(0.3)
        street_full = f"{sender.street or ''} {sender.house_number or ''}".strip()
        sender_line = f"{sender.company or sender.name} • {street_full} • {sender.zip_code} {sender.city}"
        self.c.drawString(20*mm, self.height - 42*mm, sender_line)
        
        # Corporate Info (Top Right)
        self.c.setFont("Helvetica-Bold", 12)
        self.c.setFillGray(0)
        self.c.drawRightString(190*mm, self.height - 20*mm, (sender.company or sender.name or "").upper())
        
        self.c.setFont("Helvetica", 9)
        y = self.height - 25*mm
        street_full = f"{sender.street or ''} {sender.house_number or ''}".strip()
        if street_full:
            self.c.drawRightString(190*mm, y, street_full)
            y -= 4*mm
        if sender.city:
            self.c.drawRightString(190*mm, y, f"{sender.zip_code or ''} {sender.city}")
            y -= 4*mm
        if sender.phone:
            self.c.drawRightString(190*mm, y, f"Tel: {sender.phone}")
            y -= 4*mm
        if sender.email:
            self.c.drawRightString(190*mm, y, f"Email: {sender.email}")

    def _draw_address_block(self, data: SemanticExtraction):
        """Draws the recipient address window (DIN 5008)."""
        recipient = data.meta_header.recipient if data.meta_header else None
        if not recipient: return

        self.c.setFont("Helvetica", 11)
        self.c.setFillGray(0)
        
        # Window starts at ~45mm from top
        y = self.height - 50*mm
        
        lines = []
        if recipient.company: lines.append(recipient.company)
        if recipient.name: lines.append(recipient.name)
        street_full = f"{recipient.street or ''} {recipient.house_number or ''}".strip()
        if street_full: lines.append(street_full)
        if recipient.city: lines.append(f"{recipient.zip_code or ''} {recipient.city}")
        if recipient.country and recipient.country.upper() != "DE":
             lines.append(recipient.country.upper())

        for line in lines:
            self.c.drawString(20*mm, y, line)
            y -= 5*mm

    def _draw_meta_info(self, data: SemanticExtraction):
        """Draws Date and Document Numbers in the top-right block."""
        fb = data.bodies.get("finance_body")
        y = self.height - 85*mm
        self.c.setFont("Helvetica", 10)
        
        # Helper for key-value pairs
        def draw_kv(label, val, y_pos):
            if val is None: return
            self.c.setFont("Helvetica-Bold", 10)
            self.c.drawRightString(160*mm, y_pos, f"{label}:")
            self.c.setFont("Helvetica", 10)
            self.c.drawString(165*mm, y_pos, str(val))
        
        # Prefer ZUGFeRD BT-2 (invoice_date) or BT-1 (invoice_number)
        inv_date = getattr(fb, "invoice_date", None) if fb else None
        if not inv_date and data.meta_header:
            inv_date = data.meta_header.doc_date
            
        if inv_date:
            from core.utils.formatting import format_date
            draw_kv("Datum", format_date(inv_date, locale=self.locale), y)
            y -= 5*mm
            
        inv_num = getattr(fb, "invoice_number", None) if fb else None
        if not inv_num and data.meta_header:
            inv_num = data.meta_header.doc_number

        if inv_num:
            draw_kv("Beleg-Nr", inv_num, y)
            y -= 5*mm

        if fb:
            if hasattr(fb, 'order_number') and fb.order_number:
                draw_kv("Auftrag-Nr", str(fb.order_number), y)
                y -= 5*mm
            if hasattr(fb, 'customer_id') and fb.customer_id:
                draw_kv("Kunden-Nr", str(fb.customer_id), y)

    def _draw_main_title(self, data: SemanticExtraction):
        """Draws the Document Type (e.g. RECHNUNG)."""
        self.c.setFont("Helvetica-Bold", 18)
        
        # Translation logic (re-used or simplified)
        mapping = {
            "INVOICE": "Rechnung",
            "RECHNUNG": "Rechnung",
            "ORDER_CONFIRMATION": "Auftragsbestätigung",
            "DELIVERY_NOTE": "Lieferschein",
            "RECEIPT": "Quittung",
            "BANK_STATEMENT": "Kontoauszug",
            "CONTRACT": "Vertrag",
            "LETTER": "Schreiben",
            "SICK_NOTE": "Arbeitsunfähigkeitsbescheinigung",
            "REMINDER": "Mahnung"
        }
        title_tags = [mapping.get(t.upper(), t.capitalize()) for t in (data.type_tags or [])]
        title = " / ".join(list(dict.fromkeys(title_tags))) or "Dokument"
        
        self.c.drawString(20*mm, self.height - 130*mm, title.upper())
        
        # Subline for order info
        fb = data.bodies.get("finance_body")
        if fb and hasattr(fb, 'order_date') and fb.order_date:
            from core.utils.formatting import format_date
            self.c.setFont("Helvetica", 9)
            # Use localized title for order info
            label = "Ihre Bestellung vom" if self.locale == "de" else "Your order from"
            self.c.drawString(20*mm, self.height - 135*mm, f"{label} {format_date(fb.order_date, locale=self.locale)}")

    def _draw_line_items(self, data: SemanticExtraction, start_y: float) -> float:
        """Draws the table of items."""
        fb = data.bodies.get("finance_body")
        items = getattr(fb, "line_items", []) if fb else []
        if not items:
            self.c.setFont("Helvetica-Oblique", 10)
            self.c.drawString(20*mm, self.height - start_y, "Keine Positionen aufgeführt.")
            return self.height - start_y - 10*mm

        # Convert to list of lists for Table
        table_data = [["Pos", "Menge", "Einheit", "Beschreibung", "E-Preis", "Gesamt"]]
        
        for i, item in enumerate(items):
            # Support both object and dict access for resilience
            def get_val(obj, key, default=None):
                if isinstance(obj, dict): return obj.get(key, default)
                return getattr(obj, key, default)

            from core.utils.formatting import format_currency
            unit_raw = get_val(item, "unit") or "Stk"
            unit_display = self.unit_codes.get(str(unit_raw).upper(), unit_raw)

            row = [
                str(get_val(item, "pos") or i+1),
                str(get_val(item, "quantity") or "1"),
                str(unit_display),
                self._wrap_text(str(get_val(item, "description") or "Unbekannt"), 50),
                format_currency(get_val(item, 'unit_price') or 0, locale=self.locale),
                format_currency(get_val(item, 'total_price') or 0, locale=self.locale)
            ]
            table_data.append(row)

        table = Table(table_data, colWidths=[10*mm, 15*mm, 15*mm, 85*mm, 25*mm, 25*mm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LINEBELOW', (0,0), (-1,0), 1.5, colors.black),
            ('LINEBELOW', (0,1), (-1,-1), 0.5, colors.grey),
            ('ALIGN', (4,0), (-1,-1), 'RIGHT'),
        ]))
        
        tw, th = table.wrapOn(self.c, 180*mm, 200*mm)
        y = self.height - start_y - th
        table.drawOn(self.c, 20*mm, y)
        return y

    def _draw_totals(self, data: SemanticExtraction, table_y: float):
        """Draws the summary (Net, Tax, Gross) below the table."""
        fb = data.bodies.get("finance_body")
        if not fb: return
        ms = getattr(fb, "monetary_summation", None)
        if not ms: return
        
        y = table_y - 10*mm
        
        def draw_total_row(label, val, y_pos, is_gross=False):
            from core.utils.formatting import format_currency
            if val is None: return y_pos
            self.c.setFont("Helvetica-Bold" if is_gross else "Helvetica", 10)
            self.c.drawRightString(160*mm, y_pos, f"{label}:")
            fmt_val = format_currency(val, currency="€", locale=self.locale)
            self.c.drawRightString(190*mm, y_pos, fmt_val)
            if is_gross:
                # Extend lines to cover label + value
                self.c.setLineWidth(1)
                self.c.line(80*mm, y_pos + 4*mm, 190*mm, y_pos + 4*mm)
                self.c.line(80*mm, y_pos - 1*mm, 190*mm, y_pos - 1*mm)
            return y_pos - 5*mm

        def get_ms_val(key):
             if isinstance(ms, dict): return ms.get(key)
             return getattr(ms, key, None)

        y = draw_total_row("Summe Positionen", get_ms_val("line_total_amount"), y)
        y = draw_total_row("Netto Summe", get_ms_val("tax_basis_total_amount"), y)
        y = draw_total_row("Umsatzsteuer", get_ms_val("tax_total_amount"), y)

        grand = get_ms_val("grand_total_amount")
        if grand:
            y -= 2*mm # Space
            draw_total_row("RECHNUNGSBETRAG", grand, y, True)

    def _draw_footer(self, data: SemanticExtraction):
        """Draws the professional footer with bank details."""
        sender = data.meta_header.sender if data.meta_header else None
        if not sender: return

        self.c.setFont("Helvetica", 8)
        self.c.setFillGray(0.4)
        self.c.line(20*mm, 30*mm, 190*mm, 30*mm)
        
        y = 25*mm
        col1 = 20*mm
        col2 = 80*mm
        col3 = 140*mm
        
        # Col 1: Name/Address
        self.c.drawString(col1, y, sender.company or sender.name or "")
        street_full = f"{sender.street or ''} {sender.house_number or ''}".strip()
        self.c.drawString(col1, y - 4*mm, street_full)
        self.c.drawString(col1, y - 8*mm, f"{sender.zip_code or ''} {sender.city or ''}")
        
        # Col 2: Bank
        if sender.iban:
            self.c.drawString(col2, y, f"Bank: {sender.bank_name or 'Bank'}")
            self.c.drawString(col2, y - 4*mm, f"IBAN: {sender.iban}")
            if sender.bic:
                self.c.drawString(col2, y - 8*mm, f"BIC: {sender.bic}")
        
        # Col 3: Tax Info
        if sender.tax_id:
            self.c.drawString(col3, y, f"Steuernummer: {sender.tax_id}")
            

    def _wrap_text(self, text, max_chars):
        if len(text) <= max_chars: return text
        return text[:max_chars-3] + "..."
