"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/vault.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Manages physical storage of document files in a secure vault.
                Enforces immutable naming conventions using UUIDs and provides
                path resolution and cleanup services.
------------------------------------------------------------------------------
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Union

from core.models.virtual import VirtualDocument as Document


class DocumentVault:
    """
    Manages the physical storage of document files.
    Enforces immutable storage by using UUIDs as filenames.
    """

    def __init__(self, base_path: Union[str, Path] = "vault") -> None:
        """
        Initializes the DocumentVault.

        Args:
            base_path: The directory path where files should be stored.
        """
        self.base_path: Path = Path(base_path).absolute()
        self._ensure_vault_exists()

    def _ensure_vault_exists(self) -> None:
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
            The absolute path string to the stored file.

        Raises:
            FileNotFoundError: If the source path does not exist.
        """
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        target_filename = f"{doc.uuid}.pdf"
        target_path = self.base_path / target_filename

        if move:
            shutil.move(str(src), str(target_path))
        else:
            shutil.copy2(str(src), str(target_path))

        return str(target_path)

    def store_file_by_uuid(self, source_path: str, file_uuid: str, move: bool = False) -> str:
        """
        Store a physical file by UUID. Preserves the original file extension.

        Args:
            source_path: Path to the source file.
            file_uuid: The UUID to use for the target filename.
            move: If True, move the file. If False, copy.

        Returns:
            The absolute path string to the stored file.

        Raises:
            FileNotFoundError: If the source path does not exist.
        """
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        target_filename = f"{file_uuid}{src.suffix.lower()}"
        target_path = self.base_path / target_filename

        if move:
            shutil.move(str(src), str(target_path))
        else:
            shutil.copy2(str(src), str(target_path))

        return str(target_path)

    def get_file_path(self, uuid: str) -> Optional[str]:
        """
        Returns the absolute path for a given document UUID.
        Strictly resolves to .pdf as per storage convention.

        Args:
            uuid: The document or file UUID.

        Returns:
            The absolute path string or None if not within vault boundaries.
        """
        path = self.base_path / f"{uuid}.pdf"

        # Validate path is inside vault to prevent traversal attacks
        try:
            if not path.resolve().is_relative_to(self.base_path.resolve()):
                return None
        except (ValueError, OSError):
            return None

        return str(path)

    def delete_document(self, doc: Document) -> bool:
        """
        Deletes the physical file associated with a document UUID.

        Args:
            doc: The document object whose file should be deleted.

        Returns:
            True if the file was deleted successfully, False otherwise.
        """
        path_str = self.get_file_path(doc.uuid)
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
