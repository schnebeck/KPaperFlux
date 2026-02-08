"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/workers.py
Version:        1.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity (Gemini 3pro)
Description:    PyQt6 worker threads for background processing (AI Queue, 
                Import, Reprocessing, Tagging).
------------------------------------------------------------------------------
"""
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
import traceback
import time
# Core Imports
from core.pipeline import PipelineProcessor
from core.ai_analyzer import AIAnalyzer
from core.rules_engine import RulesEngine
from core.repositories.logical_repo import LogicalRepository
from core.canonizer import CanonizerService
from core.similarity import SimilarityManager

class BatchTaggingWorker(QThread):
    """
    Phase 106: Worker thread to apply tagging rules to many documents in background.
    """
    progress = pyqtSignal(int, int) # processed, total
    finished = pyqtSignal(int) # count of modified documents

    def __init__(self, db, filter_tree, rules=None, uuids=None):
        super().__init__()
        self.db = db
        self.filter_tree = filter_tree
        self.rules = rules # If None, will fetch enabled rules from Tree. Can be a single Rule.
        self.uuids = uuids # If None, will fetch all non-deleted documents
        self.is_cancelled = False

    def run(self):
        engine = RulesEngine(self.db, self.filter_tree)
        repo = LogicalRepository(self.db)

        if self.rules is None:
            rules = self.filter_tree.get_active_rules()
        elif isinstance(self.rules, list):
            rules = self.rules
        else:
            rules = [self.rules] # Single rule provided

        if not rules:
            self.finished.emit(0)
            return

        # Fetch UUIDs if not provided
        uuids = self.uuids
        if uuids is None:
            cursor = self.db.connection.cursor()
            cursor.execute("SELECT uuid FROM virtual_documents WHERE deleted = 0")
            uuids = [row[0] for row in cursor.fetchall()]

        total = len(uuids)

        modified_count = 0
        for i, uuid in enumerate(uuids):
            if self.is_cancelled:
                break

            v_doc = repo.get_by_uuid(uuid)
            if v_doc:
                if engine.apply_rules_to_entity(v_doc, rules):
                    repo.save(v_doc)
                    modified_count += 1

            if i % 10 == 0:
                self.progress.emit(i + 1, total)

        self.finished.emit(modified_count)

    def cancel(self):
        self.is_cancelled = True

class ImportWorker(QThread):
    """
    Worker thread to import documents in the background.
    """
    progress = pyqtSignal(int, str) # current_index, current_filename
    finished = pyqtSignal(int, int, list, str) # success_count, total_count, imported_uuids, error_msg

    def __init__(self, pipeline: PipelineProcessor, items: list, move_source: bool = False):
        super().__init__()
        self.pipeline = pipeline
        self.items = items # List of (path, instructions) tuples
        self.move_source = move_source
        self.is_cancelled = False

    def run(self):
        success_count = 0
        imported_uuids = []
        
        # Calculate effective total for progress reporting
        effective_total = 0
        for item in self.items:
            if isinstance(item, tuple) and item[0] == "BATCH" and isinstance(item[1], list):
                effective_total += len(item[1])
            else:
                effective_total += 1
        
        current_global_idx = 0

        try:
            for i, item in enumerate(self.items):
                if self.is_cancelled:
                    break

                # Unpack tuple or handle raw string (backward compat)
                if isinstance(item, tuple):
                    fpath, instructions = item
                else:
                    fpath = item
                    instructions = None

                # SPECIAL BATCH MODE
                if fpath == "BATCH" and isinstance(instructions, list):
                    # instructions is a LIST of doc definitions
                    
                    def batch_progress_cb(curr, sub_total):
                        # curr is 1-based from pipeline
                        self.progress.emit(current_global_idx + curr - 1, f"Document {curr}/{sub_total}")

                    try:
                        # Extract all possible file paths from instructions
                        all_paths = set()
                        for doc_instr in instructions:
                            for pg in doc_instr.get("pages", []):
                                if "file_path" in pg:
                                    all_paths.add(pg["file_path"])

                        uuids = self.pipeline.process_batch_with_instructions(
                            list(all_paths), 
                            instructions, 
                            move_source=self.move_source,
                            progress_callback=batch_progress_cb
                        )
                        if uuids:
                            success_count += len(uuids)
                            imported_uuids.extend(uuids)
                            current_global_idx += len(instructions)
                    except Exception as e:
                        print(f"Batch Import Error: {e}")
                        current_global_idx += len(instructions) # Skip ahead anyway
                    continue

                self.progress.emit(current_global_idx, fpath)

                try:
                    # Async Import: Skip AI initially
                    if instructions:
                        # Pre-Flight Instruction Mode
                        uuids = self.pipeline.process_document_with_instructions(fpath, instructions, move_source=self.move_source)
                        if uuids:
                            success_count += len(uuids)
                            imported_uuids.extend(uuids)
                    else:
                        # Legacy Default Mode
                        doc = self.pipeline.process_document(fpath, move_source=self.move_source, skip_ai=True)
                        if doc:
                            success_count += 1
                            imported_uuids.append(doc.uuid)
                    
                    current_global_idx += 1

                except Exception as e:
                    print(f"Error importing {fpath}: {e}")
                    traceback.print_exc()
                    current_global_idx += 1

            self.finished.emit(success_count, effective_total, imported_uuids, "")

        except Exception as e:
            traceback.print_exc()
            self.finished.emit(success_count, total, [], str(e))

    def cancel(self):
        self.is_cancelled = True
        self.pipeline.terminate_activity()

class ReprocessWorker(QThread):
    """
    Worker thread to reprocess documents in the background.
    """
    progress = pyqtSignal(int, str) # current_index, uuid/status
    finished = pyqtSignal(int, int, list) # success_count, total, processed_uuids

    def __init__(self, pipeline: PipelineProcessor, uuids: list[str]):
        super().__init__()
        self.pipeline = pipeline
        self.uuids = uuids
        self.is_cancelled = False

    def run(self):
        success_count = 0
        total = len(self.uuids)
        processed_uuids = []

        try:
            for i, uuid in enumerate(self.uuids):
                if self.is_cancelled:
                    break

                self.progress.emit(i, uuid)

                try:
                    # Async Reprocess: Skip AI initially (Local Extraction only)
                    doc = self.pipeline.reprocess_document(uuid, skip_ai=True)
                    if doc:
                        success_count += 1
                        processed_uuids.append(uuid)
                except Exception as e:
                    print(f"Error reprocessing {uuid}: {e}")
                    traceback.print_exc()

            self.finished.emit(success_count, total, processed_uuids)

        except Exception as e:
            traceback.print_exc()
            self.finished.emit(success_count, total, [])

    def cancel(self):
        self.is_cancelled = True


class MainLoopWorker(QThread):
    """
    Intelligent Main Loop (Stage 1+).
    Periodically checks for READY_FOR_PIPELINE documents and processes them.
    Also manages Stage 2 Queue if needed.
    """
    status_changed = pyqtSignal(str) # Status text
    progress = pyqtSignal(int, int) # completed, total
    documents_processed = pyqtSignal() # Notify UI to refresh list
    fatal_error = pyqtSignal(str, str) # title, message
    pause_state_changed = pyqtSignal(bool) # True if paused

    def __init__(self, pipeline: PipelineProcessor, filter_tree):
        super().__init__()
        self.pipeline = pipeline
        self.filter_tree = filter_tree
        self.is_running = True
        self.is_paused = False

        self.canonizer = CanonizerService(pipeline.db,
                                        filter_tree=self.filter_tree,
                                        physical_repo=pipeline.physical_repo,
                                        logical_repo=pipeline.logical_repo)

    def run(self):
        print("[MainLoop] Worker started.")
        while self.is_running:
            if self.is_paused:
                self.status_changed.emit("Paused")
                time.sleep(0.5)
                continue

            try:
                # 1. Count pending items for progress reporting
                cursor = self.pipeline.db.connection.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM virtual_documents 
                    WHERE status IN ('NEW', 'READY_FOR_PIPELINE', 'STAGE2_PENDING') 
                    AND deleted = 0
                """)
                total_pending = int(cursor.fetchone()[0] or 0)

                # If nothing to do, wait and continue
                if total_pending == 0:
                    self.status_changed.emit("Idle")
                    self.progress.emit(0, 0)
                else:
                    self.status_changed.emit(f"Processing ({total_pending} remaining)")
                    
                    # Track batch progress for the UI burst
                    burst_total = min(5, total_pending)
                    processed_in_this_run = 0

                    for i in range(burst_total):
                        if not self.is_running:
                            print("[MainLoop] Stop requested mid-batch.")
                            break
                        if self.is_paused:
                            print("[MainLoop] Pause requested mid-batch.")
                            self.status_changed.emit("Finishing current & Pausing...")
                            break
                            
                        processed_count = self.canonizer.process_pending_documents(limit=1)
                        if processed_count == 0:
                            break
                        
                        processed_in_this_run += processed_count
                        total_pending -= processed_count
                        # Emit (processed_so_far, total_in_this_burst)
                        self.progress.emit(processed_in_this_run, burst_total)
                        self.status_changed.emit(f"Processing ({total_pending} remaining)")
                        # Phase 110: Immediate UI feedback
                        self.documents_processed.emit()

            except Exception as e:
                error_details = traceback.format_exc()
                print(f"[MainLoop] FATAL ERROR: {e}\n{error_details}")
                self.fatal_error.emit("Background Pipeline Error", f"A fatal error occurred in the processing pipeline:\n\n{e}")
                self.is_running = False
                break

            # Sleep until next check
            for _ in range(50): 
                if not self.is_running or self.is_paused: break
                time.sleep(0.1)
        
        print("[MainLoop] Worker stopped.")
        self.status_changed.emit("Stopped")

    def set_paused(self, paused: bool):
        self.is_paused = paused
        state = "PAUSED" if paused else "RESUMED"
        print(f"[MainLoop] {state} requested.")
        if paused:
            self.status_changed.emit("Finishing current & Pausing...")
        else:
             self.status_changed.emit("Resuming...")

        self.pause_state_changed.emit(paused)

    def stop(self):
        print("[MainLoop] STOP requested.")
        self.status_changed.emit("Stopping (Finishing current)...")
        self.is_running = False
        self.is_paused = False

class SimilarityWorker(QThread):
    """
    Worker thread to calculate document similarities in the background.
    """
    progress = pyqtSignal(int, int) # processed, total
    finished = pyqtSignal(list)      # list of duplicates

    def __init__(self, db_manager, vault, threshold=0.85):
        super().__init__()
        self.sim_manager = SimilarityManager(db_manager, vault)
        self.threshold = threshold

    def run(self):
        try:
            duplicates = self.sim_manager.find_duplicates(
                threshold=self.threshold,
                progress_callback=self._on_progress
            )
            self.finished.emit(duplicates)
        except Exception as e:
            print(f"Similarity Worker Error: {e}")
            traceback.print_exc()
            self.finished.emit([])

    def _on_progress(self, current, total):
        self.progress.emit(current, total)

class MatchAnalysisWorker(QThread):
    """
    Heavy lifting for PDF comparison (Alignment, CV2, Overlays) in background.
    """
    finished = pyqtSignal(str) # temp_pdf_path
    error = pyqtSignal(str)

    def __init__(self, left_path, right_path, engine):
        super().__init__()
        self.left_path = left_path
        self.right_path = right_path
        self.engine = engine

    def run(self):
        import fitz
        import cv2
        import tempfile
        import os

        try:
            m_doc_native = fitz.open(self.left_path)
            m_doc_scan = fitz.open(self.right_path)
            
            diff_pdf = fitz.open()
            num_pages = m_doc_native.page_count
            
            print(f"[MatchAnalysis] Background Pre-calculating {num_pages} pages...")
            
            for i in range(num_pages):
                p_rect = m_doc_native[i].rect
                page = diff_pdf.new_page(width=p_rect.width, height=p_rect.height)
                
                # Render (lower DPI for speed? Using 130 for now)
                img_native = self.engine.pdf_page_to_numpy(m_doc_native, i, dpi=130)
                scan_idx = min(i, m_doc_scan.page_count - 1)
                img_scan = self.engine.pdf_page_to_numpy(m_doc_scan, scan_idx, dpi=130)
                
                aligned_scan, _ = self.engine.align_and_compare(img_native, img_scan)
                diff_overlay = self.engine.create_diff_overlay(img_native, aligned_scan)
                
                is_success, buffer = cv2.imencode(".png", diff_overlay)
                if is_success:
                    page.insert_image(p_rect, stream=buffer.tobytes())

            fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix="diff_precalc_")
            os.close(fd)
            diff_pdf.save(temp_path)
            diff_pdf.close()
            m_doc_native.close()
            m_doc_scan.close()
            
            self.finished.emit(temp_path)
        except Exception as e:
            self.error.emit(str(e))
