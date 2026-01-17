import pytest
import os
import zipfile
import pandas as pd
from datetime import datetime
from core.document import Document
from core.exporter import DocumentExporter

def test_export_to_zip(tmp_path):
    # Setup Data
    doc1 = Document(
        uuid="uuid1",
        original_filename="invoice.pdf",
        doc_date="2023-10-25",
        amount=123.45,
        sender="Amazon",
        file_path=str(tmp_path / "invoice.pdf")
    )
    # Create dummy PDF file
    with open(doc1.file_path, "w") as f:
        f.write("PDF Content")
        
    doc2 = Document(
        uuid="uuid2", 
        original_filename="receipt.pdf",
        amount="50.00", # String amount to test conversion
        sender="Edeka"
    )
    # doc2 has no file
    
    documents = [doc1, doc2]
    
    zip_path = tmp_path / "export.zip"
    
    # Execute Export
    DocumentExporter.export_to_zip(documents, str(zip_path), include_pdfs=True)
    
    assert os.path.exists(zip_path)
    
    # Verify ZIP Content
    with zipfile.ZipFile(zip_path, 'r') as zf:
        file_list = zf.namelist()
        print(f"ZIP Content: {file_list}")
        
        # Check Manifest
        assert "manifest.xlsx" in file_list
        
        # Check PDF in subfolder
        # export_filename defaults to original_filename if empty
        assert "documents/invoice.pdf" in file_list
        assert "documents/receipt.pdf" not in file_list # No file path
        
        # Verify Manifest Content
        # Pandas requires openpyxl
        with zf.open("manifest.xlsx") as excel_file:
            df = pd.read_excel(excel_file)
            
            # Check Columns
            assert "Amount (Net)" in df.columns
            assert "Date" in df.columns
            assert "File Link" in df.columns
            
            # Check Values & Types
            # Row 0: Amazon
            row0 = df.iloc[0]
            assert row0["Sender"] == "Amazon"
            assert row0["Amount (Net)"] == 123.45
            assert isinstance(row0["Amount (Net)"], (float, int))
            
            # Date check
            # Pandas reads dates as Timestamp
            assert pd.to_datetime(row0["Date"]) == pd.Timestamp("2023-10-25")
            
            # Check ID
            assert row0["ID"] == "uuid1"
            
            # Check Hyperlink Formula (pandas might read value or formula dep. on engine)
            # But the column 'File Link' should act as link.
            # Row 0 has link
            # Excel formulas aren't heavily parsed by read_excel by default usually.
            # But we can check content.
            # Note: read_excel might return the display text or NaN for formulas depending on openpyxl.
            # But we generated it with xlsxwriter.
