"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/semantic_exporter.py
Version:        1.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Exports Semantic Document Structure (JSON) to multi-sheet 
                Excel files. Standardizes extraction from layout blocks like 
                tables, key-value pairs, and addresses.
------------------------------------------------------------------------------
"""

from typing import Any, Callable, Dict, List, Optional

import pandas as pd


class SemanticExcelExporter:
    """
    Exports a Semantic Document Structure (JSON) to a multi-sheet Excel file.
    Handles various layout block types including tables, key-values, and stamps.
    """

    def __init__(self, semantic_data: Dict[str, Any]) -> None:
        """
        Initializes the SemanticExcelExporter.

        Args:
            semantic_data: The structured semantic metadata of a document.
        """
        self.data: Dict[str, Any] = semantic_data

    def export(self, output_path: str) -> None:
        """
        Generates the Excel file at the specified path.

        Args:
            output_path: Destination file path for the .xlsx file.
        """
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 1. Summary Sheet
            self._write_summary(writer)

            # 2. Key-Value Pairs Sheet
            self._write_key_values(writer)

            # 3. Tables Sheet(s)
            self._write_tables(writer)

            # 4. Addresses Sheet
            self._write_addresses(writer)

            # 5. Text Content Sheet
            self._write_text_content(writer)

            # 6. Stamps Sheet
            self._write_stamps(writer)

    def _write_summary(self, writer: pd.ExcelWriter) -> None:
        """Writes the document summary sheet."""
        summary = self.data.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}

        # Normalize doc_type if list
        dt = summary.get("doc_type")
        if isinstance(dt, list):
            dt = ", ".join(map(str, dt))

        df = pd.DataFrame([{
            "Document Type": dt,
            "Date": summary.get("main_date"),
            "Language": summary.get("language")
        }])
        df.to_excel(writer, sheet_name="Summary", index=False)

    def _traverse_blocks(self, block_type: str, callback: Callable[[Any, Dict[str, Any]], None]) -> None:
        """
        Helper to traverse all blocks of a specific type and fire a callback.

        Args:
            block_type: The block type to filter for (e.g., 'table', 'address').
            callback: Function(page_num, block_dict) to call for each matching block.
        """
        pages = self.data.get("pages", [])
        if not isinstance(pages, list):
            return

        for page in pages:
            if not isinstance(page, dict):
                continue
            p_num = page.get("page_number", "?")
            regions = page.get("regions", [])
            if not isinstance(regions, list):
                continue
            for region in regions:
                if not isinstance(region, dict):
                    continue
                blocks = region.get("blocks", [])
                if not isinstance(blocks, list):
                    continue
                for block in blocks:
                    if isinstance(block, dict) and block.get("type") == block_type:
                        callback(p_num, block)

    def _write_key_values(self, writer: pd.ExcelWriter) -> None:
        """Writes key-value pairs to the Excel writer."""
        rows: List[Dict[str, Any]] = []

        def handler(page: Any, block: Dict[str, Any]) -> None:
            pairs = block.get("pairs", [])
            if isinstance(pairs, list):
                for pair in pairs:
                    if isinstance(pair, dict):
                        rows.append({
                            "Page": page,
                            "Key": pair.get("key"),
                            "Value": pair.get("value")
                        })

        self._traverse_blocks("key_value", handler)

        if rows:
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name="Key-Values", index=False)

    def _write_addresses(self, writer: pd.ExcelWriter) -> None:
        """Writes addresses to the Excel writer."""
        rows: List[Dict[str, Any]] = []

        def handler(page: Any, block: Dict[str, Any]) -> None:
            structured = block.get("structured", {})
            if not isinstance(structured, dict):
                structured = {}
            rows.append({
                "Page": page,
                "Role": block.get("role"),
                "Name": structured.get("name"),
                "Street": structured.get("street"),
                "City": structured.get("city"),
                "Raw": block.get("raw_text")
            })

        self._traverse_blocks("address", handler)

        if rows:
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name="Addresses", index=False)

    def _write_text_content(self, writer: pd.ExcelWriter) -> None:
        """Writes prose text blocks to the Excel writer."""
        rows: List[Dict[str, Any]] = []

        def handler(page: Any, block: Dict[str, Any]) -> None:
            rows.append({
                "Page": page,
                "Style": block.get("style"),
                "Content": block.get("content")
            })

        self._traverse_blocks("text", handler)

        if rows:
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name="Text Content", index=False)

    def _write_stamps(self, writer: pd.ExcelWriter) -> None:
        """Writes stamp/seal detections to the Excel writer."""
        rows: List[Dict[str, Any]] = []

        def handler(page: Any, block: Dict[str, Any]) -> None:
            rows.append({
                "Page": page,
                "Text": block.get("text"),
                "Date": block.get("date"),
                "Color": block.get("color"),
                "Shape": block.get("shape")
            })

        self._traverse_blocks("stamp", handler)

        if rows:
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name="Stamps", index=False)

    def _write_tables(self, writer: pd.ExcelWriter) -> None:
        """
        Writes tables to Excel.
        Priority:
        1. Top-level 'tables' (Consolidated/Merged across pages).
        2. Fallback: Page-level 'table' blocks (Fragmented).
        """
        consolidated_tables = self.data.get("tables", [])

        if isinstance(consolidated_tables, list) and consolidated_tables:
            # Plan A: Write Consolidated Tables
            for i, table in enumerate(consolidated_tables):
                if not isinstance(table, dict):
                    continue
                headers = table.get("headers", [])
                rows = table.get("rows", [])

                purpose = table.get("purpose", "")
                if purpose and "item" in str(purpose).lower():
                    sheet_name = f"Table_LineItems_{i+1}"
                else:
                    sheet_name = f"Table_{i+1}"

                self._write_single_table(writer, headers, rows, sheet_name)
        else:
            # Plan B: Fragmented Tables (Fallback to page blocks)
            count = 0

            def handler(page: Any, block: Dict[str, Any]) -> None:
                nonlocal count
                headers = block.get("headers", [])
                rows = block.get("rows", [])

                count += 1
                sheet_name = f"Table_P{page}_{count}"
                self._write_single_table(writer, headers, rows, sheet_name)

            self._traverse_blocks("table", handler)

    def _write_single_table(self, writer: pd.ExcelWriter, headers: List[Any], rows: List[List[Any]], sheet_name: str) -> None:
        """Helper to write a single DataFrame to a sheet."""
        if not isinstance(rows, list) or not rows:
            return

        if not isinstance(headers, list) or not headers:
            headers = [f"Col_{i}" for i in range(len(rows[0]))]

        # Ensure row length matches headers
        cleaned_rows = []
        for r in rows:
            if not isinstance(r, list):
                continue
            if len(r) > len(headers):
                r = r[:len(headers)]  # truncate
            elif len(r) < len(headers):
                r = r + [None] * (len(headers) - len(r))  # pad
            cleaned_rows.append(r)

        if cleaned_rows:
            df = pd.DataFrame(cleaned_rows, columns=headers)
            # Excel sheet names are limited to 31 chars
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
