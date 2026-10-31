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

import shutil
from pathlib import Path
from typing import Optional, Union

from core.logger import get_logger
from core.models.virtual import VirtualDocument as Document

logger = get_logger("vault")

# Derived artifacts (e.g. OCR'd searchable copies) live in a subdirectory so the
# WORM originals in the vault root are never touched and integrity scans
# (files in the vault root only) do not mistake them for ghost files.
DERIVED_DIR_NAME: str = "derived"
SEARCHABLE_SUFFIX: str = ".searchable.pdf"
STAMPED_SUFFIX: str = ".stamped.pdf"


def searchable_path_for(original_path: Union[str, Path]) -> Path:
    """
    Returns the location of the derived searchable (OCR'd) copy of a vault file.

    Args:
        original_path: Path of the original (WORM) vault file.

    Returns:
        Path '<vault>/derived/<uuid>.searchable.pdf' (may not exist).
    """
    original = Path(original_path)
    return original.parent / DERIVED_DIR_NAME / f"{original.stem}{SEARCHABLE_SUFFIX}"


def stamped_path_for(original_path: Union[str, Path]) -> Path:
    """
    Returns the location of the derived stamped copy of a vault file.

    Args:
        original_path: Path of the original (WORM) vault file.

    Returns:
        Path '<vault>/derived/<uuid>.stamped.pdf' (may not exist).
    """
    original = Path(original_path)
    return original.parent / DERIVED_DIR_NAME / f"{original.stem}{STAMPED_SUFFIX}"


def store_searchable_copy(original_path: Union[str, Path], ocr_output: Union[str, Path]) -> Path:
    """
    Stores an OCR'd PDF as derived artifact of a vault file. The original is
    never modified.

    Args:
        original_path: Path of the original (WORM) vault file.
        ocr_output: The OCR'd PDF to store.

    Returns:
        Path of the stored derived copy.
    """
    target = searchable_path_for(original_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(ocr_output), str(target))
    return target


def resolve_view_path(original_path: Union[str, Path]) -> str:
    """
    Returns the path to display for a vault file: the derived stamped copy,
    else the derived searchable copy, else the original.

    Args:
        original_path: Path of the original vault file.

    Returns:
        Path string to open for viewing.
    """
    for derived in (stamped_path_for(original_path), searchable_path_for(original_path)):
        if derived.exists():
            return str(derived)
    return str(original_path)


def remove_derived_files(original_path: Union[str, Path]) -> None:
    """
    Deletes derived artifacts of a vault file (call when the original is purged).

    Args:
        original_path: Path of the original vault file.
    """
    for derived in (searchable_path_for(original_path), stamped_path_for(original_path)):
        if derived.exists():
            try:
                derived.unlink()
            except OSError as e:
                logger.warning(f"Failed to remove derived file {derived}: {e}")


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
                remove_derived_files(path)
                return True
            except OSError:
                return False
        return False
