import subprocess
import tempfile
import os
from typing import Optional
from pathlib import Path
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
        # If vault/db are injected, utilize them. If not, create defaults.
        # Note: base_path argument is becoming redundant if we fully switch to Config, 
        # but kept for backward compatibility/tests.
        self.vault = vault if vault else DocumentVault(self.config.get_vault_path())
        self.db = db if db else DatabaseManager(db_path)
        
    def process_document(self, file_path: str) -> Optional[Document]:
        """
        Main entry point:
        1. Create Document object
        2. Store file in Vault
        3. OCR the file (if needed)
        4. AI Analysis (Sender, Amount, Date)
        5. Save metadata to DB
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 1. Create Document
        doc = Document(original_filename=path.name)
        
        # 2. Store in Vault
        stored_path = self.vault.store_document(doc, str(path))
        if not stored_path:
            return None # Failed to store
            
        # 3. OCR
        try:
            doc.text_content = self._run_ocr(Path(stored_path))
        except Exception as e:
            print(f"OCR Error: {e}")
            # Continue even if OCR fails, maybe AI can look at image later? 
            # For now text is needed for AI.
            doc.text_content = ""
            
        # 4. AI Analysis
        self._run_ai_analysis(doc)
            
        # 5. Save to DB
        self.db.insert_document(doc)
        
        return doc

    def reprocess_document(self, uuid: str) -> Optional[Document]:
        """
        Reprocess an existing document:
        1.  Fetch from DB
        2.  Locate in Vault
        3.  Re-run OCR
        4.  Update DB
        """
        doc = self.db.get_document_by_uuid(uuid)
        if not doc:
            return None
            
        file_path = self.vault.get_file_path(doc.uuid)
        if not file_path or not Path(file_path).exists():
            print(f"File not found in vault: {file_path}")
            return None
            
        # Re-run OCR
        try:
            doc.text_content = self._run_ocr(Path(file_path))
        except Exception as e:
            print(f"OCR Error during reprocess: {e}")
            
        # Re-run AI
        self._run_ai_analysis(doc)
        
        # Update DB (Using insert/replace for now as we don't have update_document)
        self.db.insert_document(doc)
        
        return doc
        
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
            
        except Exception as e:
            print(f"AI Pipeline Error: {e}")
