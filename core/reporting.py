"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/reporting.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Reporting engine for KPaperFlux. Handles financial aggregation,
                monthly summary calculation, and Excel-optimized CSV exports.
------------------------------------------------------------------------------
"""

import csv
import io
import logging
from decimal import Decimal
from typing import Dict, List, Any, BinaryIO

from core.models.virtual import VirtualDocument

logger = logging.getLogger("KPaperFlux.Reporting")


class ReportGenerator:
    """Core reporting engine."""

    @staticmethod
    def get_monthly_summary(documents: List[Any]) -> Dict[str, Dict[str, Decimal]]:
        """Groups financial totals by YYYY-MM, returning net/gross/tax."""
        monthly: Dict[str, Dict[str, Decimal]] = {}
        
        for doc in documents:
            doc_date = None
            if hasattr(doc, "semantic_data") and doc.semantic_data and doc.semantic_data.meta_header:
                doc_date = doc.semantic_data.meta_header.doc_date
            
            if not doc_date: continue
            try:
                month_key = "-".join(doc_date.split("-")[:2])
                if len(month_key) != 7: continue
                
                if month_key not in monthly:
                    monthly[month_key] = {"net": Decimal("0.00"), "gross": Decimal("0.00"), "tax": Decimal("0.00")}
                
                if hasattr(doc.semantic_data, "bodies") and "finance_body" in doc.semantic_data.bodies:
                    fb = doc.semantic_data.bodies["finance_body"]
                    monthly[month_key]["net"] += Decimal(str(getattr(fb, "total_net", 0) or 0))
                    monthly[month_key]["gross"] += Decimal(str(getattr(fb, "total_gross", 0) or 0))
                    monthly[month_key]["tax"] += Decimal(str(getattr(fb, "total_tax", 0) or 0))
                else:
                    amt = getattr(doc, "total_amount", 0) or 0
                    monthly[month_key]["gross"] += Decimal(str(amt))
            except Exception as e:
                logger.warning(f"Error in monthly summary: {e}")
                
        return dict(sorted(monthly.items(), reverse=True))

    @staticmethod
    def get_tax_summary(documents: List[Any]) -> Dict[str, Decimal]:
        """Aggregates all tax amounts grouped by tax rate string (e.g., '19%')."""
        tax_agg: Dict[str, Decimal] = {}
        for doc in documents:
            if not hasattr(doc, "semantic_data") or not doc.semantic_data or "finance_body" not in doc.semantic_data.bodies:
                continue
            fb = doc.semantic_data.bodies["finance_body"]
            td = getattr(fb, "tax_details", {})
            if isinstance(td, dict):
                for rate, amount in td.items():
                    tax_agg[rate] = tax_agg.get(rate, Decimal("0.00")) + Decimal(str(amount))
        return dict(sorted(tax_agg.items()))

    @staticmethod
    def export_to_csv(documents: List[Any]) -> bytes:
        """Returns CSV bytes optimized for Excel."""
        output = io.BytesIO()
        output.write(b'\xef\xbb\xbf')
        wrapper = io.TextIOWrapper(output, encoding='utf-8', newline='')
        writer = csv.writer(wrapper, delimiter=';')
        
        writer.writerow(["Date", "Sender", "Amount", "Currency", "Type", "DocNumber", "Filename"])
        
        for doc in documents:
            sender_name = "N/A"
            doc_date = "N/A"
            doc_num = "N/A"
            currency = "EUR"
            
            if hasattr(doc, "semantic_data") and doc.semantic_data and doc.semantic_data.meta_header:
                mh = doc.semantic_data.meta_header
                doc_date = mh.doc_date or "N/A"
                doc_num = mh.doc_number or "N/A"
                if mh.sender:
                    sender_name = mh.sender.company or mh.sender.name or "N/A"
            
            writer.writerow([
                doc_date,
                sender_name,
                f"{getattr(doc, 'total_amount', 0):.2f}" if getattr(doc, 'total_amount', None) is not None else "0.00",
                currency,
                getattr(doc, "effective_type", "UNKNOWN"),
                doc_num,
                getattr(doc, "original_filename", "N/A")
            ])
            
        wrapper.flush()
        return output.getvalue()
