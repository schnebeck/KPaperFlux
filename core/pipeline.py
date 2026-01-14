from pathlib import Path
from core.document import Document
from core.vault import DocumentVault
from core.database import DatabaseManager

class PipelineProcessor:
    """
    Orchestrates the document import and processing flow.
    """
    
    def __init__(self, vault: DocumentVault, db: DatabaseManager):
        self.vault = vault
        self.db = db

    def process_document(self, source_path: str) -> Document:
        """
        Full processing pipeline:
        1.  Validate source
        2.  Create Document object
        3.  OCR (Extract text)
        4.  AI Analysis (Metadata)
        5.  Store in Vault
        6.  Store in DB
        """
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
            
        # 1. Create Document
        doc = Document(original_filename=path.name)
        
        # 2. OCR Step (Placeholder for now)
        doc.text_content = self._run_ocr(path)
        
        # 3. AI Step (Placeholder for now)
        self._run_ai_analysis(doc)
        
        # 4. Vault Storage
        # The vault copies the file and returns the new path
        self.vault.store_document(doc, str(path))
        
        # 5. Database Storage
        self.db.insert_document(doc)
        
        return doc

    def _run_ocr(self, path: Path) -> str:
        """
        Mockable OCR step.
        Real implementation would use OCRmyPDF or Tesseract.
        """
        # TODO: Implement real OCR
        return ""

    def _run_ai_analysis(self, doc: Document):
        """
        Mockable AI step.
        Real implementation would call Google Gemini API.
        """
        # TODO: Implement real AI analysis
        pass
