
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
from core.vocabulary import VocabularyManager
from pdf2image import convert_from_path
import re

class PipelineProcessor:
    """
    Coordinator for document ingestion, processing, and storage.
    """
    def __init__(self, base_path: str = "vault", db_path: str = "kpaperflux.db", 
                 vault: Optional[DocumentVault] = None, db: Optional[DatabaseManager] = None):
        
        self.config = AppConfig()
        self.vault = vault if vault else DocumentVault(self.config.get_vault_path())
        self.db = db if db else DatabaseManager(db_path)
        self.vocabulary = VocabularyManager()
        
    def process_document(self, file_path: str, move_source: bool = False, skip_ai: bool = False) -> Optional[Document]:
        """
        Main entry point:
        1. Create Document object
        2. Store file in Vault (Copy or Move)
        3. Determine Type (Native vs Scanned)
        4. Extract Text (Native or OCR)
        5. AI Analysis (Optional via skip_ai)
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
        # 3 & 4. Text Extraction Strategy
        doc.text_content = self._detect_and_extract_text(doc, full_stored_path)
            
        # 5. AI Analysis
        if not skip_ai:
             self._run_ai_analysis(doc, full_stored_path)
            
        # 6. Save to DB
        doc.last_processed_at = datetime.datetime.now().isoformat()
        doc.export_filename = self._generate_export_filename(doc)
        self.db.insert_document(doc)
        
        # 7. Canonization (CDM Extraction) - Phase 98
        # We run this immediately if AI was used
        if not skip_ai:
            try:
                from core.canonizer import CanonizerService
                # We instantiate service on demand (or store in self if preferred)
                # But Analyzer is temporary? PipelineProcessor creates analyzer inside _run_ai?
                # Actually _run_ai uses AIAnalyzer. We should reuse it or generic one.
                # Let's instantiate Canonizer.
                canonizer = CanonizerService(self.db)
                canonizer.process_document(doc.uuid, doc.text_content, doc.semantic_data)
            except Exception as e:
                print(f"Canonization Error [{doc.uuid}]: {e}")
        
        return doc

    def reprocess_document(self, uuid: str, skip_ai: bool = False) -> Optional[Document]:
        """
        Reprocess an existing document:
        1.  Fetch from DB
        2.  Locate in Vault
        3.  Re-run Extraction
        4.  Update DB
        """
        doc = self.db.get_document_by_uuid(uuid)
        if not doc:
            return None
            
        file_path = self.vault.get_file_path(doc.uuid)
        if not file_path or not Path(file_path).exists():
            print(f"File not found in vault: {file_path}")
            return None
            
        # Re-run Extraction
        doc.text_content = self._detect_and_extract_text(doc, Path(file_path))
            
        # Re-run AI
        if not skip_ai:
            self._run_ai_analysis(doc, file_path)
        
        # Recalculate Page Count (in case it was missing or file changed)
        if hasattr(doc, 'page_count'): # Ensure field exists on doc model
             doc.page_count = self._calculate_page_count(Path(file_path))
             
        # Backfill created_at if missing
        if not doc.created_at:
             doc.created_at = datetime.datetime.now().isoformat()
        
        # Update DB
        doc.last_processed_at = datetime.datetime.now().isoformat()
        doc.export_filename = self._generate_export_filename(doc)
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
                        
                self._run_ai_analysis(new_doc, stored_path)
                new_doc.export_filename = self._generate_export_filename(new_doc)
                self.db.insert_document(new_doc)
                
                return new_doc
                
        except Exception as e:
            print(f"Merge Error: {e}")
            return None
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
        return None

    def _detect_and_extract_text(self, doc: Document, path: Path) -> str:
        """
        Determine if Native or Scanned and extract text accordingly.
        """
        try:
            if self._is_native_pdf(path):
                print(f"[{doc.uuid}] Detected Native PDF. Extracting text directly.")
                text = self._extract_text_native(path)
                # Fallback check
                if len(text.strip()) < 50:
                    print(f"[{doc.uuid}] Native text insufficient (<50 chars). Falling back to OCR.")
                    return self._run_ocr(path)
                return text
            else:
                print(f"[{doc.uuid}] Detected Scanned PDF/Image. Running OCR.")
                return self._run_ocr(path)
        except Exception as e:
            print(f"Extraction Error [{doc.uuid}]: {e}")
            return ""

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

    def _run_ai_analysis(self, doc: Document, file_path: str = None):
        """
        Run AI Analysis on the document text + Image (Multimodal).
        Updates the doc object with extracted metadata.
        """
        api_key = os.environ.get("GEMINI_API_KEY") # Or config
        # Phase 95/102: SWITCH TO CANONIZER SERVICE
        # Replaced Legacy AI Analysis with new Semantic Canonizer logic
        # This fixes the issue where Re-Analyze used the old 'Generic Prompt'
        from core.canonizer import CanonizerService
        from core.config import AppConfig
        
        # Instantiate Canonizer (lightweight)
        # Note: Canonizer initializes its own AIAnalyzer if none is passed.
        canonizer = CanonizerService(self.db)
        
        print(f"[{doc.uuid}] Starting Intelligent Analysis (Stage 1 & 2)...")
        # Process Document (Split, Classify, Extract) -> Semantic Entities
        # This handles the cleanup, prompt strategies, and multi-doc support.
        # Phase 103: Pass file_path for Visual Audit (Stage 1.5)
        canonizer.process_document(doc.uuid, doc.text_content, file_path=file_path)
        
        # We save the document state to ensure last_modified is updated
        self.db.update_document(doc)
        
        # Note: The mapping of semantic data to 'doc' columns is deferred 
        # or handled by the 'CompositeDocument' logic in the UI.
        
        
        # Legacy mapping removed (Phase 102).
        # Semantic data now lives in 'semantic_entities' table.
            
    def _generate_export_filename(self, doc: Document) -> str:
        """
        Generate a standardized export filename base.
        Pattern: Sender_Type_Date
        """
        sender = doc.sender or "Unknown"
        if doc.sender_company:
             sender = doc.sender_company
        elif doc.sender_name:
             sender = doc.sender_name
             
        doc_type = doc.doc_type or "Document"
        date_part = str(doc.doc_date) if doc.doc_date else "UnknownDate"
        
        def clean(s):
             # Remove invalid chars for filenames
             s = str(s).strip()
             s = re.sub(r'[^\w\s-]', '', s) # Keep word chars, space, dash
             s = re.sub(r'[\s]+', '_', s)   # Space to underscore
             return s
             
        base = f"{clean(sender)}_{clean(doc_type)}_{clean(date_part)}"
        return base
