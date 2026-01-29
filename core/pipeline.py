
import subprocess
import tempfile
import os
from typing import Optional, List, Union, Any
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

import hashlib
import uuid
from core.models.physical import PhysicalFile
from core.models.virtual import VirtualDocument, SourceReference
from core.repositories import PhysicalRepository, LogicalRepository

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
        
        # Repositories (Phase 2.0)
        self.physical_repo = PhysicalRepository(self.db)
        self.logical_repo = LogicalRepository(self.db)
        self.current_process = None

    def terminate_activity(self):
        """Forcefully terminate any running subprocess."""
        if self.current_process:
            try:
                print(f"[Pipeline] Terminating subprocess PID {self.current_process.pid}...")
                self.current_process.kill()
            except Exception as e:
                print(f"Error killing process: {e}")
            self.current_process = None

    def _compute_sha256(self, path: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _virtual_to_legacy(self, virtual_doc: VirtualDocument) -> Document:
        """
        Convert VirtualDocument back to legacy Document for compatibility.
        """
        # Reconstruct text content
        full_text = []
        original_filename = "virtual_doc.pdf"
        
        # Resolve sources to get text and filename
        if virtual_doc.source_mapping:
            # Iterate sources
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
            # extra_data specific to legacy handling?
            extra_data={"status": virtual_doc.status}
        )
        return doc
        
    def _ingest_physical_file(self, file_path: str, move_source: bool = False) -> Optional[PhysicalFile]:
        """
        Stage 0 Phase A: Physical Ingestion (Vault + OCR -> PhysicalFile).
        Handles Hashing, Dedup, Vault Storage, and OCR.
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
            text_map = {}
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
                raw_ocr_data=text_map, # Stored as Dict/JSON
                created_at=datetime.datetime.now().isoformat()
            )
            self.physical_repo.save(phys_file)
            print(f"[Phase A] Imported new physical file: {file_uuid}")
        else:
            print(f"[Phase A] Dedup: Using existing physical file {phys_file.uuid}")
            if move_source:
                 try: os.remove(file_path)
                 except: pass # Best effort
                 
        return phys_file

    def process_document(self, file_path: str, move_source: bool = False, skip_ai: bool = False) -> Optional[Document]:
        """
        Legacy/Default Ingest: One File -> One Document.
        """
        phys_file = self._ingest_physical_file(file_path, move_source)
        if not phys_file: return None

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
        
        # Increment ref count (handled by DB or manual call)
        # self.physical_repo.increment_ref_count(phys_file.uuid)
        
        # --- Phase C: Persistence ---
        # 1. Shadow Insert (Legacy Persistence) - Must come FIRST for FK constraints (source_doc_uuid -> documents.uuid)
        legacy_doc = self._virtual_to_legacy(v_doc)
        # Backfill physical props
        legacy_doc.phash = phys_file.phash 
        legacy_doc.page_count = phys_file.page_count_phys
        legacy_doc.created_at = v_doc.created_at
        legacy_doc.last_processed_at = datetime.datetime.now().isoformat()
        legacy_doc.export_filename = self._generate_export_filename(legacy_doc)
        
        # REMOVED Phase 4: No longer inserting into Shadow Table (View)
        # self.db.insert_document(legacy_doc, create_default_entity=False)

        # 2. Save Logical Entity
        self.logical_repo.save(v_doc)
        print(f"[Phase C] Persisted VirtualDocument: {new_uuid}")
        
        # 3. AI Analysis
        if not skip_ai:
             self._run_ai_analysis(v_doc, None) # path not needed for v_doc logic handled in canonizer
            
        return legacy_doc

    def reprocess_document(self, uuid: str, skip_ai: bool = False) -> Optional[Document]:
        """
        Reprocess an existing document:
        1.  Try Logical Entity (V2)
        2.  Fallback to Legacy
        """
        # A. Try Logical Entity (V2)
        v_doc = self.logical_repo.get_by_uuid(uuid)
        
        if v_doc:
            if not skip_ai:
                 # Helper to get file path for visual audit
                 f_path = None
                 if v_doc.source_mapping:
                     pf = self.physical_repo.get_by_uuid(v_doc.source_mapping[0].file_uuid)
                     if pf: f_path = pf.file_path
                 
                 # AI analysis simplified or redirected to Stage 0/1 logic
                 pass
            
            # Refresh
            v_doc = self.logical_repo.get_by_uuid(uuid)
            return self._virtual_to_legacy(v_doc)
            
        else:
            # B. Legacy Fallback
            doc = self.db.get_document_by_uuid(uuid)
            if not doc:
                return None
            
            file_path = self.vault.get_file_path(doc.uuid)
            # Re-run AI
            if not skip_ai:
                self._run_ai_analysis(doc, file_path)
                
            return self.db.get_document_by_uuid(uuid)
    
    def split_entity(self, entity_uuid: str, split_after_page_index: int) -> tuple[str, str]:
        """
        Delegate to CanonizerService to split manual entity.
        Returns UUIDs of the two resulting entities.
        """
        from core.canonizer import CanonizerService
        canonizer = CanonizerService(self.db, physical_repo=self.physical_repo, logical_repo=self.logical_repo)
        return canonizer.split_entity(entity_uuid, split_after_page_index)

    def restructure_file(self, file_uuid: str, new_mappings: list[list[dict]]) -> list[str]:
        """
        Delegate to CanonizerService to completely restructure a file's entities.
        """
        from core.canonizer import CanonizerService
        canonizer = CanonizerService(self.db, physical_repo=self.physical_repo, logical_repo=self.logical_repo)
        return canonizer.restructure_file_entities(file_uuid, new_mappings)

    def update_entity_structure(self, entity_uuid: str, new_mapping: list) -> bool:
        """
        Update the structure (pages/rotation) of an existing entity.
        If mapping is empty, deletes the entity.
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

    def apply_restructure_instructions(self, original_entity_uuid: str, instructions: list) -> list[str]:
        """
        Atomically replace an existing entity (or entities) with new ones.
        1. Capture physical sources of old doc.
        2. Delete old doc.
        3. Create new docs from instructions.
        4. Cleanup orphaned files.
        """
        old_doc = self.logical_repo.get_by_uuid(original_entity_uuid)
        if not old_doc:
            # Fallback: maybe it's already deleted or a new import.
            # Handle as batch if no original.
            return []

        file_uuids_to_check = [ref.file_uuid for ref in old_doc.source_mapping]
        created_at = old_doc.created_at
        
        # 1. Delete Original
        self.logical_repo.delete_by_uuid(original_entity_uuid)
        
        # 2. Create New
        new_uuids = []
        for instr in instructions:
            pages_data = instr.get("pages", [])
            if not pages_data: continue
            
            mapping = []
            current_file_uuid = None
            current_rot = -1
            current_pages = []
            
            for p in pages_data:
                f_uuid = p.get("file_uuid")
                # Fallback if uuid missing but path exists
                if not f_uuid and p.get("file_path"):
                     # Try finding by path (expensive but safe fallback)
                     f_path = p.get("file_path")
                     for check_uid in file_uuids_to_check:
                         pf = self.physical_repo.get_by_uuid(check_uid)
                         if pf and pf.file_path == f_path:
                             f_uuid = check_uid
                             break
                
                if not f_uuid: continue
                
                p_idx = p["file_page_index"] + 1
                rot = p.get("rotation", 0)
                
                if f_uuid == current_file_uuid and rot == current_rot:
                    current_pages.append(p_idx)
                else:
                    if current_pages:
                        mapping.append(SourceReference(current_file_uuid, current_pages, current_rot))
                    current_file_uuid = f_uuid
                    current_rot = rot
                    current_pages = [p_idx]
            
            if current_pages:
                mapping.append(SourceReference(current_file_uuid, current_pages, current_rot))
                
            if mapping:
                new_doc = VirtualDocument(
                    uuid=str(uuid.uuid4()),
                    source_mapping=mapping,
                    status="READY_FOR_PIPELINE",
                    created_at=created_at,
                    last_processed_at=datetime.datetime.now().isoformat(),
                    type_tags=["MANUAL_EDIT"]
                )
                self.logical_repo.save(new_doc)
                new_uuids.append(new_doc.uuid)
        
        # 3. Cleanup
        self.physical_cleanup(file_uuids_to_check)
        return new_uuids

    def delete_entity(self, entity_uuid: str) -> bool:
        """
        Hard delete an entity and cleanup orphaned physical files.
        """
        v_doc = self.logical_repo.get_by_uuid(entity_uuid)
        if not v_doc: return False
        
        file_uuids_to_check = [ref.file_uuid for ref in v_doc.source_mapping]
        
        # 1. Delete Entity
        self.logical_repo.delete_by_uuid(entity_uuid)
        print(f"[Pipeline] Deleted Entity {entity_uuid}")
        
        # 2. Cleanup orphaned files
        self.physical_cleanup(file_uuids_to_check)
        return True

    def physical_cleanup(self, file_uuids: list[str]):
        """
        Check if physical files are still referenced by any logical entities.
        If not, delete the file from Vault and Database.
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
                        except Exception as e:
                            print(f"[Pipeline] Error removing vault file: {e}")
                    
                    # Remove from Database
                    with self.db.connection:
                         self.db.connection.execute("DELETE FROM physical_files WHERE uuid = ?", (f_uuid,))
                         print(f"[Pipeline] Removed record from physical_files: {f_uuid}")

    def process_document_with_instructions(self, file_path: str, instructions: list, move_source: bool = False) -> list[str]:
        """
        Stage 0 (Instruction-Based):
        1. Ingest Physical File.
        2. Create N Logical Entities based on `instructions` payload.
        3. Return list of new Entity UUIDs.
        
        Instructions format: [{"page_range": [start_0, end_0]}, ...]
        """
        phys_file = self._ingest_physical_file(file_path, move_source)
        if not phys_file: return []
        
        new_uuids = []
        
        for instr in instructions:
            if "pages" in instr:
                 # New Granular Logic (Rotation/Deletion)
                 page_data = instr["pages"]
                 if not page_data: continue
                 
                 mapping = []
                 # Group by Rotation. 
                 current_rot = -1
                 current_pages = []
                 
                 for p in page_data:
                     # 0-based index from frontend -> 1-based for Backend
                     p_idx = p["file_page_index"] + 1
                     rot = p.get("rotation", 0)
                     
                     if current_rot == -1:
                         current_rot = rot
                         current_pages.append(p_idx)
                     elif rot == current_rot:
                         current_pages.append(p_idx)
                     else:
                         # Flush current group
                         mapping.append(SourceReference(
                             file_uuid=phys_file.uuid, 
                             pages=current_pages, 
                             rotation=current_rot
                         ))
                         # Start new
                         current_rot = rot
                         current_pages = [p_idx]
                         
                 # Flush last
                 if current_pages:
                     mapping.append(SourceReference(
                         file_uuid=phys_file.uuid, 
                         pages=current_pages, 
                         rotation=current_rot
                     ))
                 
            elif "page_range" in instr:
                # Legacy Range Logic
                start, end = instr["page_range"]
                page_list = list(range(start + 1, end + 2))
                mapping = [SourceReference(file_uuid=phys_file.uuid, pages=page_list, rotation=0)]
            else:
                continue
            
            v_doc = VirtualDocument(
                uuid=str(uuid.uuid4()),
                source_mapping=mapping,
                status="READY_FOR_PIPELINE", # Pre-Approved Structure
                created_at=datetime.datetime.now().isoformat()
            )
            self.logical_repo.save(v_doc)
            new_uuids.append(v_doc.uuid)
            
        print(f"[Stage 0] Created {len(new_uuids)} entities from instructions.")
        return new_uuids

    def process_batch_with_instructions(self, file_paths: list[str], instructions: list, move_source: bool = False) -> list[str]:
        """
        Stage 0 (Batch Instruction-Based):
        1. Ingest all physical files.
        2. Create N Logical Entities based on `instructions` payload, which can reference multiple files.
        3. Return list of new Entity UUIDs.
        """
        # 1. Ingest all
        path_to_uuid = {}
        for path in file_paths:
            phys = self._ingest_physical_file(path, move_source)
            if phys:
                path_to_uuid[path] = phys.uuid
        
        new_uuids = []
        
        # 2. Process Instructions
        for instr in instructions:
            pages_data = instr.get("pages", [])
            if not pages_data: continue
            
            mapping = []
            # Group by (file_uuid, rotation) to minimize SourceReference entries
            current_file_uuid = None
            current_rot = -1
            current_pages = []
            
            for p in pages_data:
                f_path = p.get("file_path")
                f_uuid = path_to_uuid.get(f_path)
                if not f_uuid: continue
                
                p_idx = p["file_page_index"] + 1
                rot = p.get("rotation", 0)
                
                if f_uuid == current_file_uuid and rot == current_rot:
                    current_pages.append(p_idx)
                else:
                    # Flush
                    if current_pages:
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
            if current_pages:
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

    def merge_documents(self, uuids: list[str]) -> bool:
        """
        Merge multiple documents LOGICALLY into a new entity.
        Originals are kept.
        """
        if not uuids:
            return False
            
        new_mapping = []
        created_at = None
        
        for uid in uuids:
            v_doc = self.logical_repo.get_by_uuid(uid)
            if v_doc:
                if not created_at: created_at = v_doc.created_at
                new_mapping.extend(v_doc.source_mapping)
        
        if not new_mapping:
            return False
            
        merged_doc = VirtualDocument(
            uuid=str(uuid.uuid4()),
            source_mapping=new_mapping,
            status="READY_FOR_PIPELINE",
            created_at=created_at or datetime.datetime.now().isoformat(),
            last_processed_at=datetime.datetime.now().isoformat(),
            type_tags=["LOGICAL_MERGE"]
        )
        self.logical_repo.save(merged_doc)
        print(f"[Pipeline] Logically merged {len(uuids)} documents into {merged_doc.uuid}")
        return True

    def merge_documents_physical(self, uuids: List[str]) -> Optional[Document]:
        """
        Old physical merge implementation. (Keep for reference/export tools)
        """

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

    def _extract_text_native(self, path: Path) -> dict:
        """
        Extract text from native PDF using pdfminer, returning page map.
        Returns: {1: "text...", 2: "text..."}
        """
        try:
            from pdfminer.high_level import extract_text
            # Just loop pages? Efficient? 
            # Better to use extract_pages for single pass, but extract_text is easier.
            # Get Page Count
            pages = self._calculate_page_count(path)
            result = {}
            for i in range(pages):
                text = extract_text(path, page_numbers=[i])
                if text.strip():
                    result[str(i+1)] = text
            return result
        except ImportError:
            print("pdfminer not found")
            return {}
        except Exception as e:
            print(f"Native extraction error: {e}")
            return {}

    def _run_ocr(self, path: Path) -> dict:
        """
        Execute OCRmyPDF to extract text, then extract per-page.
        """
        ocr_binary = self.config.get_ocr_binary()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_pdf = Path(temp_dir) / f"ocr_{path.name}"
            # sidecar_txt = Path(temp_dir) / f"ocr_{path.name}.txt"
            
            # Run ocrmypdf with quality enhancements
            # Run ocrmypdf with speed optimizations
            cmd = [
                ocr_binary,
                "--skip-text",    # Only OCR what needs it
                "--jobs", "4",    # Parallel processing
                "-l", "deu+eng",
                # removed expensive image preprocessing for speed
                str(path), 
                str(output_pdf)
            ]
            
            # Execute with process tracking
            try:
                self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = self.current_process.communicate()
                
                if self.current_process.returncode != 0:
                     print(f"OCR Error: {stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                 print(f"Subprocess Error: {e}")
                 if self.current_process:
                     try: self.current_process.kill() 
                     except: pass
            finally:
                self.current_process = None
            
            if output_pdf.exists():
                # Extract text from the OCR'd PDF using native extractor
                return self._extract_text_native(output_pdf)
                
        return {}
            
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

    def _run_ai_analysis(self, doc_obj: Union[Document, VirtualDocument], file_path: str = None):
        """
        Run AI Analysis on the document.
        Supports both Legacy Document and VirtualDocument.
        """
        api_key = self.config.get_api_key() # Use config getter
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
                 # Update the DTO with new data so save_document works if called later?
                 # Actually, process_virtual_document saves internally to repo?
                 # pipeline.save_document() updates the VirtualDoc from the DTO.
                 # Analyzers usually Update the Entity directly.
             else:
                 print(f"[{doc_obj.uuid}] Error: Could not resolve to VirtualDocument.")
        else:
             print(f"[{getattr(doc_obj, 'uuid', '?')}] Unknown object type for analysis.")

            
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
    def save_document(self, doc: Document):
        """
        Save an updated Legacy Document DTO to the V2 Backend.
        Maps DTO fields back to VirtualDocument and persists via LogicalRepo.
        """
        # 1. Fetch existing Entity
        virtual_doc = self.logical_repo.get_by_uuid(doc.uuid)
        if not virtual_doc:
            print(f"[Pipeline] Warning: Attempting to save non-existent entity {doc.uuid}")
            return
            
        # 2. Update Fields
        virtual_doc.sender_name = doc.sender
        virtual_doc.doc_date = doc.doc_date
        # Amount isn't a top-level field in VirtualDoc yet? 
        # It's in semantic_data['summary']['amount'] usually.
        # But we should ensure semantic_data is synced.
        
        if doc.semantic_data:
            virtual_doc.semantic_data = doc.semantic_data
            
        # Also ensure summary reflects top level overrides if any
        if not virtual_doc.semantic_data:
             virtual_doc.semantic_data = {}
        
        # Phase 45: Ensure Financials in Semantic Data
        # If doc.amount is set, write to semantic_data if missing
        if doc.amount is not None:
             if 'summary' not in virtual_doc.semantic_data:
                 virtual_doc.semantic_data['summary'] = {}
             virtual_doc.semantic_data['summary']['net_amount'] = float(doc.amount) # approximate mapping
             
        # 3. Save
        self.logical_repo.save(virtual_doc)
