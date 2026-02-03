"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/exporter.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Export service for bundling documents into ZIP archives with
                Excel manifest files. Handles metadata translation and localized
                formatting.
------------------------------------------------------------------------------
"""

import os
import tempfile
import zipfile
from datetime import date as d_date
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from core.models.virtual import VirtualDocument as Document
from core.metadata_normalizer import MetadataNormalizer
from core.semantic_translator import SemanticTranslator


class DocumentExporter:
    """
    Handles exporting documents to ZIP archives containing an Excel manifest
    and optional PDF files.
    """

    @staticmethod
    def export_to_zip(
        documents: List[Document], output_path: str, include_pdfs: bool = True, progress_callback: Optional[Callable[[int], None]] = None
    ) -> None:
        """
        Export documents to a ZIP file.

        Args:
            documents: List of Document objects to export.
            output_path: Destination path for the .zip file.
            include_pdfs: Whether to include PDF files in a 'documents/' subfolder.
            progress_callback: Optional callable(int) for percentage progress.
        """

        # 1. Resolve Unique Filenames
        unique_filenames: Dict[str, str] = {}  # uuid -> filename
        used_names: set[str] = set()

        for doc in documents:
            base_name = doc.export_filename if doc.export_filename else doc.original_filename
            if not base_name:
                base_name = f"document_{doc.uuid}"

            # Remove extension if accidentally double-added or ensure it
            # But let's respect original extension? Assume .pdf for now or keep original.
            # Usually we expect PDF.
            name, ext = os.path.splitext(base_name)
            if not ext:
                ext = ".pdf"

            final_name = f"{name}{ext}"
            counter = 1
            while final_name in used_names:
                final_name = f"{name} ({counter}){ext}"
                counter += 1

            used_names.add(final_name)
            unique_filenames[doc.uuid] = final_name

        # 2. Prepare Data for DataFrame
        data: List[Dict[str, Any]] = []
        translator = SemanticTranslator.instance()

        # Pre-scan schema to determine all possible columns from type_definitions
        # This ensures consistent column order and existence even if docs are empty
        config = MetadataNormalizer.get_config()
        all_field_ids: set[str] = set()
        if config and "types" in config:
            for t_def in config["types"].values():
                for f in t_def.get("fields", []):
                    all_field_ids.add(f["id"])

        # Helper to format headers
        # We will use keys for DataFrame but rename later for Excel

        for i, doc in enumerate(documents):
            # Parse Date
            doc_date = doc.doc_date
            dt: Optional[datetime] = None
            if doc_date:
                if isinstance(doc_date, (datetime, d_date)):
                    dt = doc_date
                elif isinstance(doc_date, str):
                    try:
                        # doc_date from V2 model is usually YYYY-MM-DD
                        dt = datetime.strptime(doc_date, "%Y-%m-%d")
                    except ValueError:
                        # Try ISO if full timestamp
                        try:
                            dt = datetime.fromisoformat(doc_date)
                        except ValueError:
                            dt = None


            # Parse Amounts (ensure float)
            def to_float(val: Any) -> float:
                if not val:
                    return 0.0
                if isinstance(val, (float, int)):
                    return float(val)
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0.0

            # Determine export filename
            filename = unique_filenames.get(doc.uuid)

            # Basic Columns
            row: Dict[str, Any] = {
                "Date": dt,
                "Sender": doc.sender_name or "Unknown",
                "Content": doc.text_content,
                "Amount (Net)": to_float(doc.total_net or doc.total_amount),
                "Tax Rate": to_float(doc.total_tax),
                "Gross Amount": to_float(doc.total_gross),
                "Currency": doc.currency,
                "Recipient": doc.recipient_name,
                "IBAN": doc.iban,
                "Filename": filename,
                "ID": doc.uuid,
            }


            # Semantic Columns (Phase 86)
            # Normalize to get flat dictionary of details
            semantic_details = MetadataNormalizer.normalize_metadata(doc)

            # Add to row, prefixed or just as is?
            # Let's prefix to avoid collision or just overwrite?
            # Standard fields (IBAN, Tax) might duplicate.
            # We prefer the explicitly mapped ones above if they exist,
            # but semantic_details might have "tax_amount" which is "Tax Amount".

            for k, v in semantic_details.items():
                # Translate key to label for consistency?
                # Or keep ID and rename columns later?
                # Dataframe needs unique keys.
                # Let's use the ID for now.
                if k not in row:  # Don't overwrite core fields like 'Date' (main_date)
                    row[k] = v

            # Hyperlink Placeholder
            if include_pdfs:
                # Excel Hyperlink Formula: HYPERLINK("path", "friendly_name")
                # Paths in ZIP are typically forward slash
                row["File Link"] = f'=HYPERLINK("documents/{filename}", "Open PDF")'

            data.append(row)

            if progress_callback and i % 10 == 0:
                progress = int((i / len(documents)) * 30)  # First 30% is prep
                progress_callback(progress)

        df = pd.DataFrame(data)

        # Rename Columns using Semantic Translator
        # We need to map field_ids to Labels
        # AND Core columns are already English "Date", "Amount".
        # Should we localize them too? Yes, user expects German.

        rename_map: Dict[str, str] = {
            "Date": translator.tr("Date"),
            "Sender": translator.tr("Sender"),
            "Content": translator.tr("Content"),
            "Amount (Net)": translator.tr("Net Amount"),
            "Tax Rate": translator.tr("Tax Rate"),
            "Gross Amount": translator.tr("Gross Amount"),
            "Currency": translator.tr("Currency"),
            "Recipient": translator.tr("Recipient"),
            "IBAN": translator.tr("IBAN"),
            "Filename": translator.tr("Filename"),
            "ID": "UUID",
            "File Link": translator.tr("File Link"),
        }

        # Add dynamic fields
        for field_id in all_field_ids:
            # Find definition to get label_key
            # Inefficient loop but safe
            label_key = field_id  # fallback
            for t_def in config["types"].values():
                for f in t_def.get("fields", []):
                    if f["id"] == field_id:
                        label_key = f.get("label_key", field_id)
                        break

            # Translate
            rename_map[field_id] = translator.translate(label_key)

        df.rename(columns=rename_map, inplace=True)

        # 3. Create ZIP File
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:

            # 4. Add PDFs
            if include_pdfs:
                for i, doc in enumerate(documents):
                    if doc.file_path and os.path.exists(doc.file_path):
                        # Name inside ZIP
                        arcname = f"documents/{unique_filenames.get(doc.uuid)}"
                        zf.write(doc.file_path, arcname)

                    if progress_callback and i % 5 == 0:
                        # 30% to 80%
                        progress = 30 + int((i / len(documents)) * 50)
                        progress_callback(progress)

            # 5. Write Excel to Bytes
            excel_filename = "manifest.xlsx"
            excel_path = os.path.join(tempfile.gettempdir(), f"manifest_{os.getpid()}.xlsx")

            try:
                # Use xlsxwriter for better formatting support
                with pd.ExcelWriter(excel_path, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Documents")

                    # Formatting
                    workbook = writer.book
                    worksheet = writer.sheets["Documents"]

                    # Formats
                    money_fmt = workbook.add_format({"num_format": "#,##0.00"})
                    date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd"})

                    # Auto-adjust columns
                    for i, col in enumerate(df.columns):
                        # Simple heuristic
                        width = 20
                        col_str = str(col).lower()
                        if "amount" in col_str or "betrag" in col_str or "rate" in col_str:
                            worksheet.set_column(i, i, 15, money_fmt)
                        elif "date" in col_str or "datum" in col_str:
                            worksheet.set_column(i, i, 15, date_fmt)
                        elif "content" in col_str or "inhalt" in col_str:
                            worksheet.set_column(i, i, 50)  # Wider for text
                        else:
                            worksheet.set_column(i, i, 25)

                # Add Excel to ZIP
                zf.write(excel_path, excel_filename)

            finally:
                if os.path.exists(excel_path):
                    os.remove(excel_path)

            if progress_callback:
                progress_callback(100)
