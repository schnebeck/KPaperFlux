import os
import zipfile
import pandas as pd
from typing import List
from datetime import datetime
from core.document import Document

class DocumentExporter:
    """
    Handles exporting documents to ZIP archives containing an Excel manifest 
    and optional PDF files.
    """
    
    @staticmethod
    def export_to_zip(documents: List[Document], output_path: str, include_pdfs: bool = True, progress_callback=None):
        """
        Export documents to a ZIP file.
        
        Args:
            documents: List of Document objects to export.
            output_path: Destination path for the .zip file.
            include_pdfs: Whether to include PDF files in a 'documents/' subfolder.
            progress_callback: Optional callable(int) for percentage progress.
        """
        
        # 1. Resolve Unique Filenames
        unique_filenames = {} # uuid -> filename
        used_names = set()

        for doc in documents:
            base_name = doc.export_filename if doc.export_filename else doc.original_filename
            if not base_name:
                base_name = f"document_{doc.uuid}"
            
            # Remove extension if accidentally double-added or ensure it
            # But let's respect original extension? Assume .pdf for now or keep original.
            # Usually we expect PDF.
            name, ext = os.path.splitext(base_name)
            if not ext: ext = ".pdf"
            
            final_name = f"{name}{ext}"
            counter = 1
            while final_name in used_names:
                final_name = f"{name} ({counter}){ext}"
                counter += 1
            
            used_names.add(final_name)
            unique_filenames[doc.uuid] = final_name

        # 2. Prepare Data for DataFrame
        data = []
        
        for i, doc in enumerate(documents):
            # Parse Date
            dt = None
            if doc.doc_date:
                # Check known types
                from datetime import date as d_date
                if isinstance(doc.doc_date, (datetime, d_date)):
                     dt = doc.doc_date
                elif isinstance(doc.doc_date, str):
                     try:
                         dt = datetime.strptime(doc.doc_date, "%Y-%m-%d")
                     except ValueError:
                         dt = None
                
            # Parse Amounts (ensure float)
            def to_float(val):
                if not val: return 0.0
                if isinstance(val, (float, int)): return float(val)
                try:
                    return float(val)
                except:
                    return 0.0

            # Determine export filename
            filename = unique_filenames.get(doc.uuid)
            
            row = {
                "Date": dt,
                "Sender": doc.sender_name or doc.sender_company or doc.sender, # Fallback
                "Content": doc.text_content, # User requested text content
                "Amount (Net)": to_float(doc.amount),
                "Tax Rate": to_float(doc.tax_rate),
                "Gross Amount": to_float(doc.gross_amount),
                "Currency": doc.currency,
                "Recipient": doc.recipient_name or doc.recipient_company,
                "IBAN": doc.iban,
                "Filename": filename,
                "ID": doc.uuid # Reference
            }
            
            # Hyperlink Placeholder
            if include_pdfs:
                 # Excel Hyperlink Formula: HYPERLINK("path", "friendly_name")
                 # Paths in ZIP are typically forward slash
                row["File Link"] = f'=HYPERLINK("documents/{filename}", "Open PDF")'
            
            data.append(row)
            
            if progress_callback and i % 10 == 0:
                progress = int((i / len(documents)) * 30) # First 30% is prep
                progress_callback(progress)

        df = pd.DataFrame(data)
        
        # 3. Create ZIP File
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            
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
            excel_path = f"/tmp/manifest_{os.getpid()}.xlsx"
            
            try:
                # Use xlsxwriter for better formatting support
                with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Documents')
                    
                    # Formatting
                    workbook = writer.book
                    worksheet = writer.sheets['Documents']
                    
                    # Money Format
                    money_fmt = workbook.add_format({'num_format': '#,##0.00'})
                    date_fmt = workbook.add_format({'num_format': 'yyyy-mm-dd'})
                    
                    # Apply formats
                    # Find column indices
                    for col_num, value in enumerate(df.columns.values):
                        if value in ["Amount (Net)", "Gross Amount", "Tax Rate"]:
                            worksheet.set_column(col_num, col_num, 15, money_fmt)
                        elif value == "Date":
                            worksheet.set_column(col_num, col_num, 15, date_fmt)
                        else:
                            worksheet.set_column(col_num, col_num, 20)
                            
                # Add Excel to ZIP
                zf.write(excel_path, excel_filename)
                
            finally:
                if os.path.exists(excel_path):
                    os.remove(excel_path)
                    
            if progress_callback:
                progress_callback(100)
