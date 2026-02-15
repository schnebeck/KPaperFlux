"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/exporters/pdf_report.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    High-fidelity PDF report generation using ReportLab.
                Handles tables, styles, and embedded charts.
------------------------------------------------------------------------------
"""

import io
import os
import datetime
import xml.sax.saxutils as saxutils
from typing import List, Dict, Any, Optional
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas

from PyQt6.QtCore import QLocale, QDateTime, QCoreApplication, Qt

class PdfReportGenerator:
    """Generates professional PDF reports from KPaperFlux report data."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.locale = QLocale()
        self.logo_path = "/home/schnebeck/Dokumente/Projects/KPaperFlux/resources/icon.png"
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Initializes KPaperFlux specific report styles."""
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=0.5 * cm,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#2c3e50")
        ))
        
        self.styles.add(ParagraphStyle(
            name='ReportSubTitle',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=1 * cm,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#7f8c8d")
        ))

        self.styles.add(ParagraphStyle(
            name='TableHeading',
            parent=self.styles['Normal'],
            fontSize=11,
            fontWeight='Bold',
            spaceAfter=0.2 * cm,
            textColor=colors.HexColor("#2c3e50")
        ))

    def generate(self, title: str, items: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None, metadata_type: str = "report_definition", pagesize=A4) -> bytes:
        """
        Generates a PDF report from a list of ordered items.
        
        Args:
            title: The report title.
            items: List of dictionaries with keys 'type' and 'value'.
            metadata: Optional dictionary to embed (Universal Exchange Format).
            metadata_type: Type of the exchange payload.
            pagesize: ReportLab pagesize (default A4).
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=pagesize, 
            rightMargin=1.5*cm, 
            leftMargin=1.5*cm, 
            topMargin=2*cm, 
            bottomMargin=2*cm
        )
        
        story = []
        
        # 1. Header
        clean_title = saxutils.escape(title)
        story.append(Paragraph(clean_title, self.styles['ReportTitle']))
        
        # Localized Date Formatting
        now_str = self.locale.toString(QDateTime.currentDateTime(), QLocale.FormatType.ShortFormat)
        meta_text = self.tr("Generated: {date}").format(date=now_str)
        story.append(Paragraph(meta_text, self.styles['ReportSubTitle']))
        
        # 2. Process Items in Order
        for item in items:
            itype = item.get("type")
            ival = item.get("value")
            
            if itype == "text" and ival:
                clean_text = ival.replace("\n", "<br/>")
                story.append(Paragraph(clean_text, self.styles['Normal']))
                story.append(Spacer(1, 0.4 * cm))
                
            elif itype == "image" and ival:
                img_stream = io.BytesIO(ival)
                img = Image(img_stream, width=17*cm, height=10*cm, kind='proportional') 
                img.hAlign = 'CENTER'
                story.append(img)
                story.append(Spacer(1, 0.5*cm))
                
            elif itype == "table" and ival:
                story.append(Spacer(1, 0.2*cm))
                headers = list(ival[0].keys())
                table_data = [headers]
                for r in ival:
                    table_data.append([self._format_val(r.get(h)) for h in headers])
                
                available_width = 18 * cm
                col_widths = [available_width / len(headers)] * len(headers)
                t = Table(table_data, hAlign='LEFT', colWidths=col_widths, repeatRows=1)
                
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f8f9fa")),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                
                for i in range(1, len(table_data)):
                    if i % 2 == 0:
                        t.setStyle(TableStyle([('BACKGROUND', (0, i), (-1, i), colors.HexColor("#f9fbff"))]))
                
                story.append(t)
                story.append(Spacer(1, 0.8 * cm))

        # Build PDF with page numbers and logo
        def add_page_number(canvas, doc):
            page_num = canvas.getPageNumber()
            width, height = doc.pagesize
            
            canvas.saveState()
            
            # --- Footer Layout ---
            canvas.setFont('Helvetica', 8)
            canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
            canvas.line(1.5*cm, 1.5*cm, width - 1.5*cm, 1.5*cm)
            
            # 1. Logo (Start of line)
            if self.logo_path and os.path.exists(self.logo_path):
                try:
                    # Draw a small version of the logo
                    logo_size = 0.8 * cm
                    canvas.drawImage(self.logo_path, 1.5*cm, 0.6*cm, width=logo_size, height=logo_size, mask='auto', preserveAspectRatio=True)
                except Exception as e:
                    print(f"Failed to draw logo in PDF: {e}")

            # 2. Page Number (Center)
            page_text = self.tr("Page {n}").format(n=page_num)
            canvas.drawCentredString(width/2.0, 1*cm, page_text)
            
            # 3. Branding (End of line)
            canvas.drawRightString(width - 1.5*cm, 1*cm, "KPaperFlux Forensic Intelligence")
            
            canvas.restoreState()
            
        doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
        pdf_bytes = buffer.getvalue()

        # 3. Post-Process with ExchangeService to embed metadata (Universal Standard)
        if metadata:
            from core.exchange import ExchangeService
            try:
                return ExchangeService.embed_in_pdf(pdf_bytes, metadata_type, metadata)
            except Exception as e:
                print(f"Failed to use ExchangeService for embedding: {e}")
                return pdf_bytes

        return pdf_bytes

    def _format_val(self, val: Any) -> str:
        """Localized value formatting."""
        if isinstance(val, (int, float, Decimal)):
            if abs(val) > 1000: # Simple heuristic for money/large numbers
                return self.locale.toString(float(val), 'f', 2)
            return self.locale.toString(float(val))
        return str(val)

    def tr(self, text: str) -> str:
        """Localized translation using Qt framework."""
        return QCoreApplication.translate("PdfReportGenerator", text)
