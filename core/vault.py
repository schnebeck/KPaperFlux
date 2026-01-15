import os
import shutil
from pathlib import Path
from core.document import Document

class DocumentVault:
    """
    Manages the physical storage of document files.
    Enforces immutable storage by using UUIDs as filenames.
    """
    
    def __init__(self, base_path: str = "vault"):
        self.base_path = Path(base_path).absolute()
        self._ensure_vault_exists()

    def _ensure_vault_exists(self):
        """Create the vault directory if it doesn't exist."""
        if not self.base_path.exists():
            self.base_path.mkdir(parents=True, exist_ok=True)

    def store_document(self, doc: Document, source_path: str, move: bool = False) -> str:
        """
        Copy or move a document file to the vault.
        Renames the file to {uuid}.pdf.
        
        Args:
            doc: The Document metadata object (must have UUID).
            source_path: Path to the source file.
            move: If True, move the file (delete source). If False, copy.
            
        Returns:
            The absolute path to the stored file.
        """
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
            
        target_filename = f"{doc.uuid}.pdf"
        target_path = self.base_path / target_filename
        
        if move:
            shutil.move(src, target_path)
        else:
            shutil.copy2(src, target_path)
        
        return str(target_path)

    def get_file_path(self, uuid: str) -> str:
        """Return the absolute path for a given document UUID."""
        # The original get_file_path logic
        path = self.base_path / f"{uuid}.pdf"
        
        # Validate path is inside vault to prevent traversal
        if not path.is_relative_to(self.base_path):
             # This might happen if we move vault location, for now safe check
             return None
        return str(path)

    def delete_document(self, doc: Document) -> bool:
        """
        Delete the physical file associated with the document.
        """
        path_str = self.get_file_path(doc.uuid) # Corrected to pass uuid
        if not path_str:
            return False
            
        path = Path(path_str)
        if path.exists():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return False
