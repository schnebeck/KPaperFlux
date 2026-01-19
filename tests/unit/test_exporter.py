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
            
            # Check Columns (Renamed)
            # "Amount (Net)" -> "Net Amount" (English Default)
            assert "Net Amount" in df.columns
            assert "Date" in df.columns
            assert "File Link" in df.columns
            
            # Semantic Field Check (Phase 86)
            # "invoice_number" -> "Invoice Number" (English Default)
            # Note: doc1 is generic, no semantic data set in test.
            
            # Check Values & Types
            # Row 0: Amazon
            row0 = df.iloc[0]
            assert row0["Sender"] == "Amazon"
            assert row0["Net Amount"] == 123.45 # Renamed Column
            assert isinstance(row0["Net Amount"], (float, int))
            
            # Date check
            # Pandas reads dates as Timestamp
            assert pd.to_datetime(row0["Date"]) == pd.Timestamp("2023-10-25")
            
            # Check ID
            assert row0["UUID"] == "uuid1" # Renamed ID -> UUID
            
            # Check Hyperlink Formula (pandas might read value or formula dep. on engine)
            # But the column 'File Link' should act as link.
            # Row 0 has link
            # Excel formulas aren't heavily parsed by read_excel by default usually.
            # But we can check content.
            # Note: read_excel might return the display text or NaN for formulas depending on openpyxl.
            # But we generated it with xlsxwriter.


def test_export_semantic_fields(tmp_path, monkeypatch):
    # Mock Config
    from core.metadata_normalizer import MetadataNormalizer
    mock_config = {
        "types": {
            "Invoice": {
                "fields": [
                    {
                        "id": "invoice_number", 
                        "label_key": "lbl_inv_num",
                        "strategies": [{"type": "json_path", "path": "summary.invoice_number"}]
                    },
                    {
                        "id": "iban", 
                        "label_key": "lbl_iban",
                        "strategies": [{"type": "json_path", "path": "summary.iban"}]
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(MetadataNormalizer, "get_config", lambda: mock_config)
    
    # Setup Doc with Semantic Data
    doc = Document(
        uuid="sem1",
        original_filename="sem.pdf",
        doc_type="Invoice"
    )
    doc.semantic_data = {
        "summary": {
            "invoice_number": "INV-2023-999",
            "iban": "DE123456789"
        }
    }
    
    zip_path = tmp_path / "semantic_export.zip"
    DocumentExporter.export_to_zip([doc], str(zip_path), include_pdfs=False)
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        with zf.open("manifest.xlsx") as excel_file:
            df = pd.read_excel(excel_file)
            
            # Check for localized/renamed columns
            # "invoice_number" -> "lbl_inv_num" (Translated or Key)
            # In test environment without proper translator setup, it returns Key or ID.
            # SemanticTranslator instance() might be singleton. 
            # If QApp not initialized, tr() returns key.
            
            print(f"Columns: {df.columns}")
            
            col_map = {c: c for c in df.columns}
            
            # Since translator might not translate "lbl_inv_num", look for it
            inv_col = next((c for c in df.columns if "lbl_inv_num" in c or "invoice_number" in c), None)
            assert inv_col is not None, f"Invoice Column not found in {df.columns}"
            
            row = df.iloc[0]
            assert row[inv_col] == "INV-2023-999"
            
            iban_col = next((c for c in df.columns if "lbl_iban" in c or "iban" in c), None)
            assert iban_col is not None
            assert row[iban_col] == "DE123456789"
