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
import datetime
from typing import List, Dict, Any, Optional
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

class PdfReportGenerator:
    """Generates professional PDF reports from KPaperFlux report data."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
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

    def generate(self, title: str, items: List[Dict[str, Any]]) -> bytes:
        """
        Generates a PDF report from a list of ordered items.
        
        Args:
            title: The report title.
            items: List of dictionaries with keys 'type' and 'value'.
                   Types: 'text' (str), 'image' (bytes), 'table' (list of dicts)
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A4, 
            rightMargin=1.5*cm, 
            leftMargin=1.5*cm, 
            topMargin=2*cm, 
            bottomMargin=2*cm
        )
        
        story = []
        
        # 1. Header
        story.append(Paragraph(title, self.styles['ReportTitle']))
        
        meta_text = self.tr("Generated: {date}").format(date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        story.append(Paragraph(meta_text, self.styles['ReportSubTitle']))
        
        # 2. Process Items in Order
        for item in items:
            itype = item.get("type")
            ival = item.get("value")
            
            if itype == "text" and ival:
                # Replace newlines with <br/> for ReportLab Paragraph
                clean_text = ival.replace("\n", "<br/>")
                story.append(Paragraph(clean_text, self.styles['Normal']))
                story.append(Spacer(1, 0.4 * cm))
                
            elif itype == "image" and ival:
                img_stream = io.BytesIO(ival)
                # Keep aspect ratio but fit within width
                img = Image(img_stream, width=17*cm, height=10*cm, kind='proportional') 
                img.hAlign = 'CENTER'
                story.append(img)
                story.append(Spacer(1, 0.5*cm))
                
            elif itype == "table" and ival:
                story.append(Spacer(1, 0.2*cm))
                # ival is expected to be table_rows list of dicts
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

        # Build PDF with page numbers
        def add_page_number(canvas, doc):
            page_num = canvas.getPageNumber()
            text = f"Page {page_num}"
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.setStrokeColor(colors.lightgrey)
            canvas.line(1.5*cm, 1.5*cm, A4[0] - 1.5*cm, 1.5*cm)
            canvas.drawCentredString(A4[0]/2.0, 1*cm, text)
            canvas.drawString(1.5*cm, 1*cm, "KPaperFlux Forensic Intelligence")
            canvas.restoreState()

        doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
        return buffer.getvalue()

    def _format_val(self, val: Any) -> str:
        if isinstance(val, (int, float, Decimal)):
            if abs(val) > 1000: # Simple heuristic for money vs index
                return f"{val:,.2f}"
            return f"{val:g}"
        return str(val)

    def tr(self, text: str) -> str:
        # Simple placeholder for translation; in a real app, this would use gettext
        return text
