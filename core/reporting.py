"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/reporting.py
Version:        2.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Reporting engine for KPaperFlux. Handles financial aggregation,
                monthly summary calculation, and Excel-optimized CSV exports.
                Uses semantic properties for improved abstraction.
------------------------------------------------------------------------------
"""

import csv
import io
import logging
from decimal import Decimal
from typing import Dict, List, Any, Optional

from core.models.virtual import VirtualDocument as Document

logger = logging.getLogger("KPaperFlux.Reporting")


class ReportGenerator:
    """Consolidated reporting and aggregation engine."""

    @staticmethod
    def get_monthly_summary(documents: List[Document]) -> Dict[str, Dict[str, Decimal]]:
        """
        Groups financial totals by YYYY-MM using semantic properties.
        Returns a dictionary of month keys with net, gross, and tax totals.
        """
        monthly: Dict[str, Dict[str, Decimal]] = {}
        
        for doc in documents:
            # Use standardized semantic properties
            doc_date = doc.doc_date
            if not doc_date or not isinstance(doc_date, str):
                continue
                
            try:
                # Expecting YYYY-MM-DD
                month_key = "-".join(doc_date.split("-")[:2])
                if len(month_key) != 7:
                    continue
                
                if month_key not in monthly:
                    monthly[month_key] = {
                        "net": Decimal("0.00"), 
                        "gross": Decimal("0.00"), 
                        "tax": Decimal("0.00")
                    }
                
                # Fetch amounts via robust semantic accessors
                gross = doc.total_gross
                net = doc.total_net
                tax = doc.total_tax
                
                # Fallback to total_amount (which maps to gross/net depending on context)
                if gross is None:
                    gross = doc.total_amount or 0.0
                
                monthly[month_key]["gross"] += Decimal(str(gross or 0))
                monthly[month_key]["net"] += Decimal(str(net or gross or 0))
                monthly[month_key]["tax"] += Decimal(str(tax or 0))
                
            except Exception as e:
                logger.warning(f"Error aggregating monthly summary for {doc.uuid}: {e}")
                
        # Sort by month descending
        return dict(sorted(monthly.items(), reverse=True))

    @staticmethod
    def get_tax_summary(documents: List[Document]) -> Dict[str, Decimal]:
        """
        Aggregates tax amounts grouped by tax rate string (e.g., '19%', '7%').
        """
        tax_agg: Dict[str, Decimal] = {}
        for doc in documents:
            if not doc.semantic_data:
                continue
                
            fb = doc.semantic_data.bodies.get("finance_body")
            if not fb:
                continue
            
            # Use tax_breakdown (EN 16931 alignment)
            tb = getattr(fb, "tax_breakdown", [])
            for row in tb:
                # Use BT-119 (tax_rate) as key
                rate = f"{float(row.tax_rate):g}%" # Format e.g. 19.0 -> '19%'
                try:
                    tax_agg[rate] = tax_agg.get(rate, Decimal("0.00")) + Decimal(str(row.tax_amount or 0))
                except (TypeError, ValueError):
                    continue
                        
        return dict(sorted(tax_agg.items()))

    @staticmethod
    def export_to_csv(documents: List[Document]) -> bytes:
        """
        Returns CSV bytes optimized for Excel (UTF-8 with BOM, semicolon delimiter).
        """
        output = io.BytesIO()
        # Add UTF-8 BOM for Excel compatibility
        output.write(b'\xef\xbb\xbf')
        
        wrapper = io.TextIOWrapper(output, encoding='utf-8', newline='')
        writer = csv.writer(wrapper, delimiter=';')
        
        # Header (English/System keys, localized headers can be added via translation layer if needed)
        writer.writerow(["Date", "Sender", "Recipient", "Amount", "Currency", "Type", "DocNumber", "Filename", "IBAN"])
        
        for doc in documents:
            try:
                writer.writerow([
                    doc.doc_date or "N/A",
                    doc.sender_name or "N/A",
                    doc.recipient_name or "N/A",
                    f"{float(doc.total_amount or 0):.2f}",
                    doc.currency or "EUR",
                    ", ".join(doc.type_tags) if doc.type_tags else "OTHER",
                    doc.doc_number or "N/A",
                    doc.original_filename or "N/A",
                    doc.iban or "N/A"
                ])
            except Exception as e:
                logger.error(f"Failed to export document {doc.uuid} to CSV: {e}")
            
        wrapper.flush()
        return output.getvalue()
