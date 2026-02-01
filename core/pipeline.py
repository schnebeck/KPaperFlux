"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/pipeline.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Coordinator for document ingestion, processing, and storage.
                Manages the transition from physical files to logical entities
                and coordinates AI analysis and vault storage.
------------------------------------------------------------------------------
"""

import datetime
import hashlib
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pikepdf
from pdf2image import convert_from_path

from core.ai_analyzer import AIAnalyzer
from core.config import AppConfig
from core.database import DatabaseManager
from core.document import Document
from core.models.physical import PhysicalFile
from core.models.virtual import SourceReference, VirtualDocument
from core.repositories import LogicalRepository, PhysicalRepository
from core.vault import DocumentVault
from core.vocabulary import VocabularyManager


class PipelineProcessor:
    """
    Coordinator for document ingestion, processing, and storage.
    """

    def __init__(
        self,
        base_path: str = "vault",
        db_path: str = "kpaperflux.db",
        vault: Optional[DocumentVault] = None,
        db: Optional[DatabaseManager] = None,
    ) -> None:
        """
        Initializes the PipelineProcessor.

        Args:
            base_path: The base path for the document vault.
            db_path: The path to the SQLite database.
            vault: Optional existing DocumentVault instance.
            db: Optional existing DatabaseManager instance.
        """
        self.config = AppConfig()
        self.vault = vault if vault else DocumentVault(self.config.get_vault_path())
        self.db = db if db else DatabaseManager(db_path)
        self.vocabulary = VocabularyManager()

        # Repositories (Phase 2.0)
        self.physical_repo = PhysicalRepository(self.db)
        self.logical_repo = LogicalRepository(self.db)
        self.current_process: Optional[subprocess.Popen] = None

    def terminate_activity(self) -> None:
        """Forcefully terminates any running subprocess."""
        if self.current_process:
            try:
                print(f"[Pipeline] Terminating subprocess PID {self.current_process.pid}...")
                self.current_process.kill()
            except ProcessLookupError:
                pass
            except Exception as e:
                print(f"Error killing process: {e}")
            self.current_process = None

    def _compute_sha256(self, path: Path) -> str:
        """
        Computes the SHA256 hash of a file.

        Args:
            path: Path to the file.

        Returns:
            The SHA256 hash as a hex string.
        """
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _virtual_to_legacy(self, virtual_doc: VirtualDocument) -> Document:
        """
        Converts a VirtualDocument back to a legacy Document for compatibility.

        Args:
            virtual_doc: The VirtualDocument to convert.

        Returns:
            A legacy Document object.
        """
        full_text: List[str] = []
        original_filename = "virtual_doc.pdf"

        # Resolve sources to get text and filename
        if virtual_doc.source_mapping:
            first = True
            for src in virtual_doc.source_mapping:
                pf = self.physical_repo.get_by_uuid(src.file_uuid)
                if pf:
                    if first:
                        original_filename = pf.original_filename
                        first = False

                    if pf.raw_ocr_data:
                        for p in src.pages:
                            full_text.append(pf.raw_ocr_data.get(str(p), ""))

        doc = Document(
            uuid=virtual_doc.uuid,
            original_filename=original_filename,
            text_content="\n".join(full_text),
            created_at=virtual_doc.created_at,
            last_processed_at=virtual_doc.last_processed_at,
            last_used=virtual_doc.last_used,
            status=virtual_doc.status,
            type_tags=virtual_doc.type_tags,
            tags=virtual_doc.tags,
            export_filename=virtual_doc.export_filename,
            deleted_at=virtual_doc.deleted_at,
            locked_at=virtual_doc.locked_at,
            exported_at=virtual_doc.exported_at,
            semantic_data=virtual_doc.semantic_data,
            extra_data={"status": virtual_doc.status, "source_mapping": virtual_doc.to_source_mapping_json()},
        )
        return doc
        
    def _ingest_physical_file(self, file_path: str, move_source: bool = False) -> Optional[PhysicalFile]:
        """
        Stage 0 Phase A: Physical Ingestion (Vault + OCR -> PhysicalFile).
        Handles Hashing, Dedup, Vault Storage, and OCR.

        Args:
            file_path: The path to the file to ingest.
            move_source: Whether to move the source file instead of copying.

        Returns:
            The created or existing PhysicalFile object, or None if ingestion failed.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        print(f"[STAGE 0] Starting Ingest for: {file_path}")
        file_sha = self._compute_sha256(path)

        # Check by SHA (Dedup)
        phys_file = self.physical_repo.get_by_phash(file_sha)

        if not phys_file:
            # 1. Store in Vault
            file_uuid = str(uuid.uuid4())
            stored_path_str = self.vault.store_file_by_uuid(file_path, file_uuid, move=move_source)
            stored_path = Path(stored_path_str)

            # 2. Extract Text / OCR
            text_map: Dict[str, str] = {}
            if self._is_native_pdf(stored_path):
                text_map = self._extract_text_native(stored_path)
                if not text_map:
                    text_map = self._run_ocr(stored_path)
            else:
                text_map = self._run_ocr(stored_path)

            # 3. Create PhysicalFile Entry
            size = stored_path.stat().st_size
            pages = self._calculate_page_count(stored_path)

            phys_file = PhysicalFile(
                uuid=file_uuid,
                original_filename=path.name,
                file_path=stored_path_str,
                phash=file_sha,
                file_size=size,
                page_count_phys=pages,
                raw_ocr_data=text_map,  # Stored as Dict/JSON
                created_at=datetime.datetime.now().isoformat(),
            )
            self.physical_repo.save(phys_file)
            print(f"[Phase A] Imported new physical file: {file_uuid}")
        else:
            print(f"[Phase A] Dedup: Using existing physical file {phys_file.uuid}")
            if move_source:
                try:
                    os.remove(file_path)
                except OSError as e:
                    print(f"Warning: Failed to remove source file after dedup: {e}")

        return phys_file

    def process_document(self, file_path: str, move_source: bool = False, skip_ai: bool = False) -> Optional[Document]:
        """
        Legacy/Default Ingest: One File -> One Document.

        Args:
            file_path: The path to the file to process.
            move_source: Whether to move the source file.
            skip_ai: Whether to skip AI analysis.

        Returns:
            The created legacy Document object.
        """
        phys_file = self._ingest_physical_file(file_path, move_source)
        if not phys_file:
            return None

        # --- Phase B: Logic ---
        # Create VirtualDocument (1:1 Mapping initially)
        new_uuid = str(uuid.uuid4())
        v_doc = VirtualDocument(
            uuid=new_uuid,
            created_at=datetime.datetime.now().isoformat(),
            status="NEW"
        )

        # Map all pages from physical file
        pages_list = list(range(1, phys_file.page_count_phys + 1))
        v_doc.add_source(phys_file.uuid, pages_list)

        # --- Phase C: Persistence ---
        # 1. Shadow Insert (Legacy Persistence)
        legacy_doc = self._virtual_to_legacy(v_doc)
        # Backfill physical props
        legacy_doc.phash = phys_file.phash
        legacy_doc.page_count = phys_file.page_count_phys
        legacy_doc.created_at = v_doc.created_at
        legacy_doc.last_processed_at = datetime.datetime.now().isoformat()
        legacy_doc.export_filename = self._generate_export_filename(legacy_doc)

        # 2. Save Logical Entity
        self.logical_repo.save(v_doc)
        print(f"[Phase C] Persisted VirtualDocument: {new_uuid}")

        # 3. AI Analysis
        if not skip_ai:
            self._run_ai_analysis(v_doc, None)

        return legacy_doc

    def reprocess_document(self, uuid_str: str, skip_ai: bool = False) -> Optional[Document]:
        """
        Reprocesses an existing document.

        Args:
            uuid_str: The UUID of the document to reprocess.
            skip_ai: Whether to skip AI analysis.

        Returns:
            The updated legacy Document object, or None if not found.
        """
        # A. Try Logical Entity (V2)
        v_doc = self.logical_repo.get_by_uuid(uuid_str)

        if v_doc:
            if not skip_ai:
                # Helper to get file path for visual audit
                f_path = None
                if v_doc.source_mapping:
                    pf = self.physical_repo.get_by_uuid(v_doc.source_mapping[0].file_uuid)
                    if pf:
                        f_path = pf.file_path

                # AI analysis logic handling (v_doc is passed to _run_ai_analysis)
                self._run_ai_analysis(v_doc, f_path)

            # Refresh
            v_doc = self.logical_repo.get_by_uuid(uuid_str)
            return self._virtual_to_legacy(v_doc)

        # B. Legacy Fallback
        doc = self.db.get_document_by_uuid(uuid_str)
        if not doc:
            return None

        file_path = self.vault.get_file_path(doc.uuid)
        # Re-run AI
        if not skip_ai:
            self._run_ai_analysis(doc, file_path)

        return self.db.get_document_by_uuid(uuid_str)
    
    def split_entity(self, entity_uuid: str, split_after_page_index: int) -> Tuple[str, str]:
        """
        Delegates to CanonizerService to split a manual entity.

        Args:
            entity_uuid: The UUID of the entity to split.
            split_after_page_index: The page index after which to split.

        Returns:
            A tuple of UUIDs for the two resulting entities.
        """
        from core.canonizer import CanonizerService

        canonizer = CanonizerService(self.db, physical_repo=self.physical_repo, logical_repo=self.logical_repo)
        return canonizer.split_entity(entity_uuid, split_after_page_index)

    def restructure_file(self, file_uuid: str, new_mappings: List[List[Dict[str, Any]]]) -> List[str]:
        """
        Delegates to CanonizerService to completely restructure a file's entities.

        Args:
            file_uuid: The UUID of the physical file.
            new_mappings: List of page mappings for new entities.

        Returns:
            A list of new entity UUIDs.
        """
        from core.canonizer import CanonizerService

        canonizer = CanonizerService(self.db, physical_repo=self.physical_repo, logical_repo=self.logical_repo)
        return canonizer.restructure_file_entities(file_uuid, new_mappings)

    def update_entity_structure(self, entity_uuid: str, new_mapping: List[Any]) -> bool:
        """
        Updates the structure (pages/rotation) of an existing entity.

        Args:
            entity_uuid: The UUID of the entity.
            new_mapping: The new page mapping.

        Returns:
            True if successful.

        Raises:
            ValueError: If the entity is not found.
        """
        v_doc = self.logical_repo.get_by_uuid(entity_uuid)
        if not v_doc:
            raise ValueError(f"Entity {entity_uuid} not found")

        file_uuids_to_check = [ref.file_uuid for ref in v_doc.source_mapping]

        if not new_mapping:
            print(f"[Pipeline] Empty mapping! Deleting entity {entity_uuid}")
            self.delete_entity(entity_uuid)
            self.physical_cleanup(file_uuids_to_check)
            return True

        v_doc.source_mapping = new_mapping
        v_doc.status = "MODIFIED"
        v_doc.last_processed_at = datetime.datetime.now().isoformat()

        self.logical_repo.save(v_doc)
        print(f"[Pipeline] Updated structure for {entity_uuid}")
        return True

    def apply_restructure_instructions(self, original_entity_uuid: str, instructions: List[Dict[str, Any]]) -> List[str]:
        """
        Atomically replaces an existing entity (or entities) with new ones.

        Args:
            original_entity_uuid: The UUID of the entity to replace.
            instructions: List of instructions for the new entities.

        Returns:
            A list of new entity UUIDs.
        """
        old_doc = self.logical_repo.get_by_uuid(original_entity_uuid)
        if not old_doc:
            return []

        file_uuids_to_check = [ref.file_uuid for ref in old_doc.source_mapping]
        created_at = old_doc.created_at

        # 1. Delete Original
        self.logical_repo.delete_by_uuid(original_entity_uuid)

        # 2. Create New
        new_uuids: List[str] = []
        for instr in instructions:
            pages_data = instr.get("pages", [])
            if not pages_data:
                continue

            mapping: List[SourceReference] = []
            current_file_uuid: Optional[str] = None
            current_rot = -1
            current_pages: List[int] = []

            for p in pages_data:
                f_uuid = p.get("file_uuid")
                # Fallback if uuid missing but path exists
                if not f_uuid and p.get("file_path"):
                    f_path = p.get("file_path")
                    for check_uid in file_uuids_to_check:
                        pf = self.physical_repo.get_by_uuid(check_uid)
                        if pf and pf.file_path == f_path:
                            f_uuid = check_uid
                            break

                if not f_uuid:
                    continue

                p_idx = p["file_page_index"] + 1
                rot = p.get("rotation", 0)

                if f_uuid == current_file_uuid and rot == current_rot:
                    current_pages.append(p_idx)
                else:
                    if current_pages and current_file_uuid:
                        mapping.append(SourceReference(current_file_uuid, current_pages, current_rot))
                    current_file_uuid = f_uuid
                    current_rot = rot
                    current_pages = [p_idx]

            if current_pages and current_file_uuid:
                mapping.append(SourceReference(current_file_uuid, current_pages, current_rot))

            if mapping:
                new_doc = VirtualDocument(
                    uuid=str(uuid.uuid4()),
                    source_mapping=mapping,
                    status="READY_FOR_PIPELINE",
                    created_at=created_at,
                    last_processed_at=datetime.datetime.now().isoformat(),
                    type_tags=["MANUAL_EDIT"],
                )
                self.logical_repo.save(new_doc)
                new_uuids.append(new_doc.uuid)

        # 3. Cleanup
        self.physical_cleanup(file_uuids_to_check)
        return new_uuids

    def delete_entity(self, entity_uuid: str) -> bool:
        """
        Hard deletes an entity and cleans up orphaned physical files.

        Args:
            entity_uuid: The UUID of the entity to delete.

        Returns:
            True if successful.
        """
        v_doc = self.logical_repo.get_by_uuid(entity_uuid)
        if not v_doc:
            return False

        file_uuids_to_check = [ref.file_uuid for ref in v_doc.source_mapping]

        # 1. Delete Entity
        self.logical_repo.delete_by_uuid(entity_uuid)
        print(f"[Pipeline] Deleted Entity {entity_uuid}")

        # 2. Cleanup orphaned files
        self.physical_cleanup(file_uuids_to_check)
        return True

    def physical_cleanup(self, file_uuids: List[str]) -> None:
        """
        Checks if physical files are still referenced by any logical entities.
        If not, deletes the file from Vault and Database.

        Args:
            file_uuids: List of physical file UUIDs to check.
        """
        for f_uuid in set(file_uuids):
            referencing_entities = self.logical_repo.get_by_source_file(f_uuid)
            if not referencing_entities:
                print(f"[Pipeline] Physical file {f_uuid} is orphaned. Purging...")
                pf = self.physical_repo.get_by_uuid(f_uuid)
                if pf:
                    # Remove from Vault
                    if pf.file_path and os.path.exists(pf.file_path):
                        try:
                            os.remove(pf.file_path)
                            print(f"[Pipeline] Removed file from vault: {pf.file_path}")
                        except OSError as e:
                            print(f"[Pipeline] Error removing vault file: {e}")

                    # Remove from Database
                    with self.db.connection:
                        self.db.connection.execute("DELETE FROM physical_files WHERE uuid = ?", (f_uuid,))
                        print(f"[Pipeline] Removed record from physical_files: {f_uuid}")

    def process_document_with_instructions(self, file_path: str, instructions: List[Dict[str, Any]], move_source: bool = False) -> List[str]:
        """
        Stage 0 (Instruction-Based):
        1. Ingest physical file.
        2. Create N logical entities based on instructions.

        Args:
            file_path: The path to the physical file.
            instructions: List of instructions for document splitting.
            move_source: Whether to move the source file.

        Returns:
            A list of new entity UUIDs.
        """
        phys_file = self._ingest_physical_file(file_path, move_source)
        if not phys_file:
            return []

        new_uuids: List[str] = []

        for instr in instructions:
            mapping: List[SourceReference] = []
            if "pages" in instr:
                page_data = instr["pages"]
                if not page_data:
                    continue

                current_rot = -1
                current_pages: List[int] = []

                for p in page_data:
                    p_idx = p["file_page_index"] + 1
                    rot = p.get("rotation", 0)

                    if current_rot == -1:
                        current_rot = rot
                        current_pages.append(p_idx)
                    elif rot == current_rot:
                        current_pages.append(p_idx)
                    else:
                        mapping.append(SourceReference(file_uuid=phys_file.uuid, pages=current_pages, rotation=current_rot))
                        current_rot = rot
                        current_pages = [p_idx]

                if current_pages:
                    mapping.append(SourceReference(file_uuid=phys_file.uuid, pages=current_pages, rotation=current_rot))

            elif "page_range" in instr:
                start, end = instr["page_range"]
                page_list = list(range(start + 1, end + 2))
                mapping = [SourceReference(file_uuid=phys_file.uuid, pages=page_list, rotation=0)]
            else:
                continue

            v_doc = VirtualDocument(
                uuid=str(uuid.uuid4()),
                source_mapping=mapping,
                status="READY_FOR_PIPELINE",
                created_at=datetime.datetime.now().isoformat(),
            )
            self.logical_repo.save(v_doc)
            new_uuids.append(v_doc.uuid)

        print(f"[Stage 0] Created {len(new_uuids)} entities from instructions.")
        return new_uuids

    def process_batch_with_instructions(self, file_paths: List[str], instructions: List[Dict[str, Any]], move_source: bool = False, progress_callback=None) -> List[str]:
        """
        Stage 0 (Batch Instruction-Based):
        1. Ingest all physical files.
        2. Create N logical entities based on instructions payload.

        Args:
            file_paths: List of paths to physical files.
            instructions: List of instructions, can reference multiple files.
            move_source: Whether to move source files.
            progress_callback: Optional callable(current, total)

        Returns:
            A list of new entity UUIDs.
        """
        # 1. Ingest all
        path_to_uuid: Dict[str, str] = {}
        for path in file_paths:
            phys = self._ingest_physical_file(path, move_source)
            if phys:
                path_to_uuid[path] = phys.uuid

        new_uuids: List[str] = []
        total_instr = len(instructions)

        # 2. Process Instructions
        for idx, instr in enumerate(instructions):
            if progress_callback:
                progress_callback(idx + 1, total_instr)
            pages_data = instr.get("pages", [])
            if not pages_data:
                continue

            mapping: List[SourceReference] = []
            # Group by (file_uuid, rotation) to minimize SourceReference entries
            current_file_uuid: Optional[str] = None
            current_rot = -1
            current_pages: List[int] = []

            for p in pages_data:
                f_path = p.get("file_path")
                f_uuid = path_to_uuid.get(f_path)
                if not f_uuid:
                    continue

                p_idx = p["file_page_index"] + 1
                rot = p.get("rotation", 0)

                if f_uuid == current_file_uuid and rot == current_rot:
                    current_pages.append(p_idx)
                else:
                    # Flush
                    if current_pages and current_file_uuid:
                        mapping.append(SourceReference(
                            file_uuid=current_file_uuid,
                            pages=current_pages,
                            rotation=current_rot
                        ))
                    # Reset
                    current_file_uuid = f_uuid
                    current_rot = rot
                    current_pages = [p_idx]

            # Flush last
            if current_pages and current_file_uuid:
                mapping.append(SourceReference(
                    file_uuid=current_file_uuid,
                    pages=current_pages,
                    rotation=current_rot
                ))

            if mapping:
                v_doc = VirtualDocument(
                    uuid=str(uuid.uuid4()),
                    source_mapping=mapping,
                    status="READY_FOR_PIPELINE",
                    created_at=datetime.datetime.now().isoformat(),
                    last_processed_at=datetime.datetime.now().isoformat()
                )
                self.logical_repo.save(v_doc)
                new_uuids.append(v_doc.uuid)

        print(f"[Stage 0 Batch] Created {len(new_uuids)} entities from instructions across {len(file_paths)} files.")
        return new_uuids

    def merge_documents(self, uuids: List[str]) -> bool:
        """
        Merges multiple documents LOGICALLY into a new entity.

        Args:
            uuids: List of entity UUIDs to merge.

        Returns:
            True if successful.
        """
        if not uuids:
            return False

        new_mapping: List[SourceReference] = []
        created_at: Optional[str] = None

        for uid in uuids:
            v_doc = self.logical_repo.get_by_uuid(uid)
            if v_doc:
                if not created_at:
                    created_at = v_doc.created_at
                new_mapping.extend(v_doc.source_mapping)

        if not new_mapping:
            return False

        merged_doc = VirtualDocument(
            uuid=str(uuid.uuid4()),
            source_mapping=new_mapping,
            status="READY_FOR_PIPELINE",
            created_at=created_at or datetime.datetime.now().isoformat(),
            last_processed_at=datetime.datetime.now().isoformat(),
            type_tags=["LOGICAL_MERGE"],
        )
        self.logical_repo.save(merged_doc)
        print(f"[Pipeline] Logically merged {len(uuids)} documents into {merged_doc.uuid}")
        return True

    def merge_documents_physical(self, uuids: List[str]) -> Optional[Document]:
        """
        Old physical merge implementation. (Keep for reference/export tools/legacy)

        Args:
            uuids: List of UUIDs to merge.

        Returns:
            Optional legacy Document object.
        """
        # (Implementation omitted or kept empty as in original)
        return None

    def _detect_and_extract_text(self, doc_uuid: str, path: Path) -> str:
        """
        Determines if Native or Scanned and extracts text accordingly.

        Args:
            doc_uuid: UUID for logging.
            path: Path to the PDF file.

        Returns:
            Extracted text content.
        """
        try:
            if self._is_native_pdf(path):
                print(f"[{doc_uuid}] Detected Native PDF. Extracting text directly.")
                text_map = self._extract_text_native(path)
                text = "\n".join(text_map.values())
                # Fallback check
                if len(text.strip()) < 50:
                    print(f"[{doc_uuid}] Native text insufficient (<50 chars). Falling back to OCR.")
                    text_map = self._run_ocr(path)
                    return "\n".join(text_map.values())
                return text
            else:
                print(f"[{doc_uuid}] Detected Scanned PDF/Image. Running OCR.")
                text_map = self._run_ocr(path)
                return "\n".join(text_map.values())
        except Exception as e:
            print(f"Extraction Error [{doc_uuid}]: {e}")
            return ""

    def _is_native_pdf(self, path: Path) -> bool:
        """
        Checks if a PDF is native (has a text layer) or a scanned image.

        Args:
            path: Path to the PDF file.

        Returns:
            True if a text layer is detected.
        """
        try:
            with pikepdf.Pdf.open(path) as pdf:
                # Heuristic: Check if pages have fonts
                for page in pdf.pages:
                    if "/Font" in page.resources:
                        return True
            return False
        except Exception as e:
            print(f"Error checking PDF native status: {e}")
            return False

    def _extract_text_native(self, path: Path) -> Dict[str, str]:
        """
        Extracts text from a native PDF using pdfminer.

        Args:
            path: Path to the PDF file.

        Returns:
            A dictionary mapping 1-based page indices to text content.
        """
        try:
            from pdfminer.high_level import extract_text

            pages = self._calculate_page_count(path)
            result: Dict[str, str] = {}
            for i in range(pages):
                text = extract_text(path, page_numbers=[i])
                if text.strip():
                    result[str(i + 1)] = text
            return result
        except ImportError:
            print("pdfminer-six not found. Install it for native PDF extraction.")
            return {}
        except Exception as e:
            print(f"Native extraction error: {e}")
            return {}

    def _run_ocr(self, path: Path) -> Dict[str, str]:
        """
        Executes OCRmyPDF to extract text from a scanned document.

        Args:
            path: Path to the source file.

        Returns:
            A dictionary mapping 1-based page indices to the OCR'd text.
        """
        ocr_binary = self.config.get_ocr_binary()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_pdf = Path(temp_dir) / f"ocr_{path.name}"

            # Run ocrmypdf with speed optimizations
            cmd = [
                ocr_binary,
                "--skip-text",  # Only OCR what needs it
                "--jobs",
                "4",  # Parallel processing
                "-l",
                "deu+eng",
                str(path),
                str(output_pdf),
            ]

            try:
                self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = self.current_process.communicate()

                if self.current_process.returncode != 0:
                    print(f"OCR Error: {stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                print(f"Subprocess Error during OCR: {e}")
                if self.current_process:
                    try:
                        self.current_process.kill()
                    except ProcessLookupError:
                        pass
            finally:
                self.current_process = None

            if output_pdf.exists():
                # Extract text from the OCR'd PDF using native extractor
                return self._extract_text_native(output_pdf)

        return {}

    def _calculate_page_count(self, path: Path) -> int:
        """
        Calculates the number of pages in a PDF.

        Args:
            path: Path to the PDF file.

        Returns:
            The number of pages, or 0 if counting failed.
        """
        try:
            with pikepdf.Pdf.open(path) as pdf:
                return len(pdf.pages)
        except Exception as e:
            print(f"Error counting pages for {path}: {e}")
            return 0

    def _run_ai_analysis(self, doc_obj: Union[Document, VirtualDocument], file_path: Optional[str] = None) -> None:
        """
        Runs AI analysis on the document.
        Supports both legacy Document and VirtualDocument objects.

        Args:
            doc_obj: The document object to analyze.
            file_path: Optional file path for visual auditing.
        """
        from core.canonizer import CanonizerService

        # Instantiate Canonizer with Repos
        canonizer = CanonizerService(self.db, physical_repo=self.physical_repo, logical_repo=self.logical_repo)

        if isinstance(doc_obj, VirtualDocument):
            print(f"[{doc_obj.uuid}] Starting Intelligent Analysis (Phase 2)...")
            canonizer.process_virtual_document(doc_obj)
        elif isinstance(doc_obj, Document):
            # Resolve DTO to VirtualDocument
            virtual_doc = self.logical_repo.get_by_uuid(doc_obj.uuid)
            if virtual_doc:
                print(f"[{doc_obj.uuid}] Resolved DTO to Entity. Starting Analysis...")
                canonizer.process_virtual_document(virtual_doc)
            else:
                print(f"[{doc_obj.uuid}] Error: Could not resolve to VirtualDocument.")
        else:
            print(f"[{getattr(doc_obj, 'uuid', '?')}] Unknown object type for analysis.")

    def _generate_export_filename(self, doc: Document) -> str:
        """
        Generates a standardized export filename base.
        Pattern: Sender_Type_Date

        Args:
            doc: The legacy Document object.

        Returns:
            The generated filename string.
        """
        sd = doc.semantic_data or {}
        sender = sd.get("sender") or "Unknown"
        if doc.sender_company:
            sender = doc.sender_company
        elif doc.sender_name:
            sender = doc.sender_name

        effective_type = "Document"
        if doc.type_tags:
            effective_type = str(doc.type_tags[0])
        date_part = str(sd.get("doc_date") or "UnknownDate")

        def clean(s: str) -> str:
            # Remove invalid chars for filenames
            s = str(s).strip()
            s = re.sub(r"[^\w\s-]", "", s)  # Keep word chars, space, dash
            s = re.sub(r"[\s]+", "_", s)  # Space to underscore
            return s

        base = f"{clean(sender)}_{clean(effective_type)}_{clean(date_part)}"
        return base

    def save_document(self, doc: Document) -> None:
        """
        Saves an updated legacy Document DTO to the V2 backend.
        Maps DTO fields back to VirtualDocument and persists via LogicalRepo.

        Args:
            doc: The legacy Document object to save.
        """
        # 1. Fetch existing Entity
        virtual_doc = self.logical_repo.get_by_uuid(doc.uuid)
        if not virtual_doc:
            print(f"[Pipeline] Warning: Attempting to save non-existent entity {doc.uuid}")
            return

        sd = doc.semantic_data or {}

        if doc.semantic_data:
            virtual_doc.semantic_data = doc.semantic_data

        if not virtual_doc.semantic_data:
            virtual_doc.semantic_data = {}

        # Ensure Financials in Semantic Data
        amt = sd.get("amount")
        if amt is not None:
            if "summary" not in virtual_doc.semantic_data:
                virtual_doc.semantic_data["summary"] = {}
            virtual_doc.semantic_data["summary"]["net_amount"] = float(amt)

        # 3. Save
        self.logical_repo.save(virtual_doc)
