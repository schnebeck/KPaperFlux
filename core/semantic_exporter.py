import pandas as pd
import json
import os
from typing import Dict, List, Any

class SemanticExcelExporter:
    """
    Exports a Semantic Document Structure (JSON) to a multi-sheet Excel file.
    """
    
    def __init__(self, semantic_data: Dict[str, Any]):
        self.data = semantic_data
        
    def export(self, output_path: str):
        """Generates the Excel file."""
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
            
        print(f"Exported to {output_path}")

    def _write_summary(self, writer):
        summary = self.data.get("summary", {})
        # Normalize doc_type if list
        dt = summary.get("doc_type")
        if isinstance(dt, list):
            dt = ", ".join(dt)
            
        df = pd.DataFrame([{
            "Document Type": dt,
            "Date": summary.get("main_date"),
            "Language": summary.get("language")
        }])
        df.to_excel(writer, sheet_name="Summary", index=False)
        
    def _traverse_blocks(self, block_type: str, callback):
        """Helper to traverse all blocks and fire callback."""
        pages = self.data.get("pages", [])
        for page in pages:
            p_num = page.get("page_number", "?")
            for region in page.get("regions", []):
                for block in region.get("blocks", []):
                    if block.get("type") == block_type:
                        callback(p_num, block)

    def _write_key_values(self, writer):
        rows = []
        def handler(page, block):
            for pair in block.get("pairs", []):
                rows.append({
                    "Page": page,
                    "Key": pair.get("key"),
                    "Value": pair.get("value")
                })
        
        self._traverse_blocks("key_value", handler)
        
        if rows:
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name="Key-Values", index=False)
            
    def _write_addresses(self, writer):
        rows = []
        def handler(page, block):
            structured = block.get("structured", {})
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

    def _write_text_content(self, writer):
        rows = []
        def handler(page, block):
            rows.append({
                "Page": page,
                "Style": block.get("style"),
                "Content": block.get("content")
            })
            
        self._traverse_blocks("text", handler)
        
        if rows:
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name="Text Content", index=False)

    def _write_stamps(self, writer):
        rows = []
        def handler(page, block):
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

    def _write_tables(self, writer):
        """
        Write tables to Excel.
        Priority: 
        1. Top-level 'tables' (Consolidated/Merged).
        2. Fallback: Page-level 'table' blocks (Fragmented).
        """
        consolidated_tables = self.data.get("tables", [])
        
        if consolidated_tables:
            # Plan A: Write Consolidated Tables
            for i, table in enumerate(consolidated_tables):
                headers = table.get("headers", [])
                rows = table.get("rows", [])
                
                # Sheet Name Logic: try "Table_LineItems" if purposeful, else "Table_1"
                purpose = table.get("purpose", "")
                if purpose and "item" in purpose:
                     sheet_name = f"Table_LineItems_{i+1}"
                else:
                     sheet_name = f"Table_{i+1}"

                self._write_single_table(writer, headers, rows, sheet_name)
        else:
            # Plan B: Fragmented Tables (Legacy/Fallback)
            count = 0
            def handler(page, block):
                nonlocal count
                headers = block.get("headers", [])
                rows = block.get("rows", [])
                
                count += 1
                sheet_name = f"Table_P{page}_{count}"
                self._write_single_table(writer, headers, rows, sheet_name)
        
            self._traverse_blocks("table", handler)
            
    def _write_single_table(self, writer, headers, rows, sheet_name):
        """Helper to write a single DataFrame to a sheet."""
        if not headers:
             if rows:
                 headers = [f"Col_{i}" for i in range(len(rows[0]))]
             else:
                 return # Empty
                 
        # Ensure row length matches headers
        cleaned_rows = []
        for r in rows:
            if len(r) > len(headers):
                r = r[:len(headers)] # truncate
            elif len(r) < len(headers):
                r = r + [None]*(len(headers)-len(r)) # pad
            cleaned_rows.append(r)

        df = pd.DataFrame(cleaned_rows, columns=headers)
        df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
