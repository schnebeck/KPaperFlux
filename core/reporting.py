"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/reporting.py
Version:        2.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Reporting engine for KPaperFlux. Handles financial aggregation,
                dynamic report execution, and Excel-optimized CSV exports.
------------------------------------------------------------------------------
"""

import csv
import io
import logging
from decimal import Decimal
from typing import Dict, List, Any, Optional

from core.models.virtual import VirtualDocument as Document
from core.models.reporting import ReportDefinition, Aggregation

import os
import json

logger = logging.getLogger("KPaperFlux.Reporting")

class ReportRegistry:
    """Singleton registry for managing report definitions."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ReportRegistry, cls).__new__(cls)
            cls._instance.reports = {}
        return cls._instance

    def load_from_directory(self, path: str):
        """Loads all .json files from the specified directory as reports."""
        self.reports.clear()
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            return

        for filename in os.listdir(path):
            if filename.endswith(".json"):
                full_path = os.path.join(path, filename)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        report = ReportDefinition(**data)
                        self.reports[report.id] = report
                        logger.info(f"Loaded report definition: {report.id}")
                except Exception as e:
                    logger.error(f"Failed to load report from {filename}: {e}")

    def get_report(self, report_id: str) -> Optional[ReportDefinition]:
        return self.reports.get(report_id)

    def list_reports(self) -> List[ReportDefinition]:
        return list(self.reports.values())


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
                
                gross = doc.total_gross
                net = doc.total_net
                tax = doc.total_tax
                
                if gross is None:
                    gross = doc.total_amount or 0.0
                
                monthly[month_key]["gross"] += Decimal(str(gross or 0))
                monthly[month_key]["net"] += Decimal(str(net or gross or 0))
                monthly[month_key]["tax"] += Decimal(str(tax or 0))
                
            except Exception as e:
                logger.warning(f"Error aggregating monthly summary for {doc.uuid}: {e}")
                
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
            
            tb = getattr(fb, "tax_breakdown", [])
            for row in tb:
                rate = f"{float(row.tax_rate):g}%"
                try:
                    tax_agg[rate] = tax_agg.get(rate, Decimal("0.00")) + Decimal(str(row.tax_amount or 0))
                except (TypeError, ValueError):
                    continue
                        
        return dict(sorted(tax_agg.items()))

    @staticmethod
    def run_custom_report(db_manager, definition: ReportDefinition) -> Dict[str, Any]:
        """
        Executes a dynamic report based on a ReportDefinition.
        Returns structured results for tables and charts.
        """
        # 1. Fetch Documents
        docs = db_manager.search_documents_advanced(definition.filter_query)
        
        results: Dict[str, Any] = {
            "definition_id": definition.id,
            "title": definition.name,
            "labels": [],
            "series": [], # List of {name: str, data: List[float]}
            "table_rows": [] # List of Dict[column, value]
        }

        if not docs:
            return results

        # 2. Grouping
        grouped_data: Dict[str, List[Document]] = {}
        group_field = definition.group_by
        
        for doc in docs:
            key = "Overall"
            if group_field:
                if group_field == "doc_date:month":
                    d = doc.doc_date
                    key = "-".join(d.split("-")[:2]) if d and isinstance(d, str) else "Unknown"
                elif group_field == "doc_date:year":
                    d = doc.doc_date
                    key = d.split("-")[0] if d and isinstance(d, str) else "Unknown"
                elif group_field == "sender":
                    key = doc.sender_name or "Unknown"
                elif group_field == "type":
                    key = doc.type_tags[0] if doc.type_tags else "OTHER"
                elif group_field.startswith("amount:"):
                    try:
                        step = float(group_field.split(":")[1])
                        val = float(doc.total_amount or 0)
                        bin_idx = int(val // step)
                        key = f"{bin_idx * step:g} - {(bin_idx + 1) * step:g}"
                    except:
                        key = "Unknown"
                else:
                    # Generic attribute/property access
                    val = getattr(doc, group_field, None)
                    if val is None and doc.semantic_data:
                        val = doc.semantic_data.get_financial_value(group_field)
                    key = str(val) if val is not None else "Unknown"
            
            if key not in grouped_data:
                grouped_data[key] = []
            grouped_data[key].append(doc)

        # Sorting labels (Handle numeric bins vs dates vs strings)
        def sort_key(k):
            if " - " in k: # Amount bin
                try: return float(k.split(" - ")[0])
                except: return k
            return k

        sorted_keys = sorted(grouped_data.keys(), key=sort_key)
        results["labels"] = sorted_keys

        # 3. Aggregation
        series_map: Dict[str, List[float]] = {f"{agg.op.upper()}({agg.field})": [] for agg in definition.aggregations}
        headers = [group_field or "Group"] + list(series_map.keys())

        # Pre-calculate totals for percent-of-total
        field_totals: Dict[str, Decimal] = {}
        for agg in definition.aggregations:
            if agg.op == "percent":
                total = Decimal("0.00")
                for doc in docs:
                    doc_val = None
                    if agg.field == "amount": doc_val = doc.total_amount
                    elif agg.field == "net": doc_val = doc.total_net
                    elif agg.field == "gross": doc_val = doc.total_gross
                    elif agg.field == "tax": doc_val = doc.total_tax
                    else:
                        if doc.semantic_data: doc_val = doc.semantic_data.get_financial_value(agg.field)
                    
                    if doc_val is not None:
                        try: total += Decimal(str(doc_val))
                        except: pass
                field_totals[agg.field] = total

        for key in sorted_keys:
            group_docs = grouped_data[key]
            row_data = {headers[0]: key}
            
            for agg in definition.aggregations:
                agg_key = f"{agg.op.upper()}({agg.field})"
                vals = []
                for doc in group_docs:
                    doc_val = None
                    if agg.field == "amount": doc_val = doc.total_amount
                    elif agg.field == "net": doc_val = doc.total_net
                    elif agg.field == "gross": doc_val = doc.total_gross
                    elif agg.field == "tax": doc_val = doc.total_tax
                    else:
                        if doc.semantic_data: doc_val = doc.semantic_data.get_financial_value(agg.field)
                    
                    if doc_val is not None:
                        try: vals.append(Decimal(str(doc_val)))
                        except: pass

                # Apply OP
                result_val = Decimal("0.00")
                if agg.op == "sum":
                    result_val = sum(vals) if vals else Decimal("0.00")
                elif agg.op == "avg":
                    result_val = (sum(vals) / len(vals)) if vals else Decimal("0.00")
                elif agg.op == "count":
                    result_val = Decimal(len(group_docs))
                elif agg.op == "min":
                    result_val = min(vals) if vals else Decimal("0.00")
                elif agg.op == "max":
                    result_val = max(vals) if vals else Decimal("0.00")
                elif agg.op == "median":
                    if vals:
                        import statistics
                        result_val = statistics.median(vals)
                elif agg.op == "percent":
                    total = field_totals.get(agg.field, Decimal("1.00"))
                    current_sum = sum(vals) if vals else Decimal("0.00")
                    result_val = (current_sum / total * 100) if total > 0 else Decimal("0.00")

                series_map[agg_key].append(float(result_val))
                row_data[agg_key] = float(result_val)
            
            results["table_rows"].append(row_data)

        for name, data in series_map.items():
            results["series"].append({"name": name, "data": data})

        return results

    @staticmethod
    def export_to_csv(documents: List[Document]) -> bytes:
        """
        Returns CSV bytes optimized for Excel (UTF-8 with BOM, semicolon delimiter).
        """
        output = io.BytesIO()
        output.write(b'\xef\xbb\xbf')
        
        wrapper = io.TextIOWrapper(output, encoding='utf-8', newline='')
        writer = csv.writer(wrapper, delimiter=';')
        
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
