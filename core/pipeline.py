
import subprocess
import tempfile
import os
from typing import Optional, List
from pathlib import Path
import pikepdf
import datetime
from core.document import Document
from core.vault import DocumentVault
from core.database import DatabaseManager
from core.ai_analyzer import AIAnalyzer
from core.config import AppConfig

class PipelineProcessor:
    """
    Coordinator for document ingestion, processing, and storage.
    """
    def __init__(self, base_path: str = "vault", db_path: str = "kpaperflux.db", 
                 vault: Optional[DocumentVault] = None, db: Optional[DatabaseManager] = None):
        
        self.config = AppConfig()
        self.vault = vault if vault else DocumentVault(self.config.get_vault_path())
        self.db = db if db else DatabaseManager(db_path)
        
    def process_document(self, file_path: str, move_source: bool = False) -> Optional[Document]:
        """
        Main entry point:
        1. Create Document object
        2. Store file in Vault (Copy or Move)
        3. Determine Type (Native vs Scanned)
        4. Extract Text (Native or OCR)
        5. AI Analysis (Sender, Amount, Date, etc.)
        6. Save metadata to DB
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 1. Create Document
        doc = Document(original_filename=path.name)
        doc.created_at = datetime.datetime.now().isoformat()
        
        # 2. Store in Vault
        stored_path = self.vault.store_document(doc, str(path), move=move_source)
        if not stored_path:
            return None # Failed to store
        
        full_stored_path = Path(stored_path)
        
        # 2.5 Calculate Page Count
        doc.page_count = self._calculate_page_count(full_stored_path)
            
        # 3 & 4. Text Extraction Strategy
        try:
            if self._is_native_pdf(full_stored_path):
                print(f"[{doc.uuid}] Detected Native PDF. Extracting text directly.")
                doc.text_content = self._extract_text_native(full_stored_path)
                # If native text extraction yields too little, fallback to OCR?
                if len(doc.text_content.strip()) < 50:
                    print(f"[{doc.uuid}] Native text insufficient (<50 chars). Falling back to OCR.")
                    doc.text_content = self._run_ocr(full_stored_path)
            else:
                print(f"[{doc.uuid}] Detected Scanned PDF/Image. Running OCR.")
                doc.text_content = self._run_ocr(full_stored_path)
        except Exception as e:
            print(f"Processing Error: {e}")
            doc.text_content = ""
            
        # 5. AI Analysis
        self._run_ai_analysis(doc)
            
        # 6. Save to DB
        self.db.insert_document(doc)
        
        return doc

    def reprocess_document(self, uuid: str) -> Optional[Document]:
        """
        Reprocess an existing document:
        1.  Fetch from DB
        2.  Locate in Vault
        3.  Re-run Extraction (Force OCR? or Auto?)
            - User request: "Reprocess (OCR)" implies forcing OCR usually.
            - But let's stick to Auto logic or allow forced mode.
            - For now: Use Auto but prioritize improvement.
        4.  Update DB
        """
        doc = self.db.get_document_by_uuid(uuid)
        if not doc:
            return None
            
        file_path = self.vault.get_file_path(doc.uuid)
        if not file_path or not Path(file_path).exists():
            print(f"File not found in vault: {file_path}")
            return None
            
        # Re-run Extraction (Force OCR for reprocess usually makes sense if native failed)
        try:
            # We assume user reprocesses because something was missing.
            # Try OCR.
            doc.text_content = self._run_ocr(Path(file_path))
        except Exception as e:
            print(f"OCR Error during reprocess: {e}")
            
            
        # Re-run AI
        self._run_ai_analysis(doc)
        
        # Recalculate Page Count (in case it was missing or file changed)
        if hasattr(doc, 'page_count'): # Ensure field exists on doc model
             doc.page_count = self._calculate_page_count(Path(file_path))
             
        # Backfill created_at if missing
        if not doc.created_at:
             doc.created_at = datetime.datetime.now().isoformat()
        
        # Update DB
        self.db.insert_document(doc)
        
        return doc
        
    def merge_documents(self, uuids: List[str]) -> Optional[Document]:
        """
        Merge multiple documents into a new one.
        Returns the new merged Document.
        Originals are NOT deleted automatically here (User decision).
        """
        if not uuids:
            return None
            
        input_paths = []
        for uuid in uuids:
            path = self.vault.get_file_path(uuid)
            if path and os.path.exists(path):
                input_paths.append(Path(path))
            else:
                print(f"Warning: merge skipping missing uuid {uuid}")
        
        if not input_paths:
            return None
            
        # Create new merged PDF
        new_doc = Document(original_filename="merged_document.pdf")
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            
        try:
            with pikepdf.Pdf.new() as pdf:
                for path in input_paths:
                    src = pikepdf.Pdf.open(path)
                    pdf.pages.extend(src.pages)
                pdf.save(tmp_path)
                
            # Store new file
            stored_path = self.vault.store_document(new_doc, tmp_path)
            
            # Process it (Extract text from new file)
            # Since it's composed of others, it might be native or mixed.
            # We process it like a fresh import.
            if stored_path:
                # We can call process_document recursively but we already stored it.
                # Just finish steps.
                full_stored_path = Path(stored_path)
                
                # Calculate Page Count
                new_doc.page_count = self._calculate_page_count(full_stored_path)
                new_doc.created_at = datetime.datetime.now().isoformat()
                
                # Copy properties? Nah, new analysis.
                if self._is_native_pdf(full_stored_path):
                        new_doc.text_content = self._extract_text_native(full_stored_path)
                else:
                        new_doc.text_content = self._run_ocr(full_stored_path)
                        
                self._run_ai_analysis(new_doc)
                self.db.insert_document(new_doc)
                
                return new_doc
                
        except Exception as e:
            print(f"Merge Error: {e}")
            return None
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
        return None

    def _is_native_pdf(self, path: Path) -> bool:
        """
        Check if PDF is native (has text layer) or scanned image.
        Heuristic: Iterate pages, check for valid text streams.
        """
        try:
            with pikepdf.Pdf.open(path) as pdf:
                # Check for /Font in resources of first page?
                # Simple check: Does extracting text return substantive content?
                # We can't rely solely on pikepdf for text extraction easily without extra tools, 
                # but we can try basic structure checks.
                # Let's use `extract_text_native` as the check implicitly? 
                # No, we want a cheap check.
                
                # Check if pages have fonts
                for page in pdf.pages:
                    if "/Font" in page.resources:
                        return True
            return False
        except Exception:
            return False

    def _extract_text_native(self, path: Path) -> str:
        """
        Extract text from native PDF using pdfminer/pikepdf tools.
        For simplicity, we use `pdfminer.high_level` if available or `subprocess pdftotext`.
        Dependency list has `ocrmypdf` which has `pdfminer.six`.
        """
        try:
            from pdfminer.high_level import extract_text
            return extract_text(path)
        except ImportError:
            # Fallback
            print("pdfminer not found, fallback to empty (will trigger OCR)")
            return ""
        except Exception as e:
            print(f"Native extraction error: {e}")
            return ""

    def _run_ocr(self, path: Path) -> str:
        """
        Execute OCRmyPDF to extract text.
        """
        ocr_binary = self.config.get_ocr_binary()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_pdf = Path(temp_dir) / f"ocr_{path.name}"
            sidecar_txt = Path(temp_dir) / f"ocr_{path.name}.txt"
            
            # Run ocrmypdf with sidecar to extract text
            # --force-ocr: rasterize vector pdfs if needed or force valid pdf
            # -l deu+eng: German and English
            cmd = [
                ocr_binary,
                "--force-ocr", 
                "-l", "deu+eng",
                "--sidecar", str(sidecar_txt),
                str(path), 
                str(output_pdf)
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            
            if sidecar_txt.exists():
                return sidecar_txt.read_text("utf-8")
                
        return ""
            
    def _calculate_page_count(self, path: Path) -> int:
        """
        Calculate number of pages in PDF.
        """
        try:
            with pikepdf.Pdf.open(path) as pdf:
                return len(pdf.pages)
        except Exception as e:
            print(f"Error counting pages for {path}: {e}")
            return 0

    def _run_ai_analysis(self, doc: Document):
        """
        Use AI Analyzer to extract metadata if API key is present.
        """
        api_key = self.config.get_api_key()
        if not api_key:
            return
            
        if not doc.text_content:
            return
            
        try:
            model_name = self.config.get_gemini_model()
            analyzer = AIAnalyzer(api_key, model_name=model_name)
            result = analyzer.analyze_text(doc.text_content)
            
            # Map result to doc
            if result.sender: doc.sender = result.sender
            if result.doc_date: doc.doc_date = result.doc_date
            if result.amount is not None: doc.amount = result.amount
            if result.doc_type: doc.doc_type = result.doc_type
            if result.sender_address: doc.sender_address = result.sender_address
            if result.iban: doc.iban = result.iban
            if result.phone: doc.phone = result.phone
            if result.tags: doc.tags = result.tags
            
            # Map Extended Address Fields
            if result.recipient_company: doc.recipient_company = result.recipient_company
            if result.recipient_name: doc.recipient_name = result.recipient_name
            if result.recipient_street: doc.recipient_street = result.recipient_street
            if result.recipient_zip: doc.recipient_zip = result.recipient_zip
            if result.recipient_city: doc.recipient_city = result.recipient_city
            if result.recipient_country: doc.recipient_country = result.recipient_country
            
            if result.sender_company: doc.sender_company = result.sender_company
            if result.sender_name: doc.sender_name = result.sender_name
            if result.sender_street: doc.sender_street = result.sender_street
            if result.sender_zip: doc.sender_zip = result.sender_zip
            if result.sender_city: doc.sender_city = result.sender_city
            if result.sender_country: doc.sender_country = result.sender_country
            
        except Exception as e:
            print(f"AI Pipeline Error: {e}")
