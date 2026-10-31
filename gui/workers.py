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
import os
import tempfile
import traceback
import time
from concurrent.futures import CancelledError
from typing import Any, Optional

import cv2
import fitz
from PyQt6 import sip
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QObject
from core.logger import get_logger, get_silent_logger

logger = get_logger("gui.workers")
# Core Imports
from core.pipeline import PipelineProcessor
from core.rules_engine import RulesEngine
from core.repositories.logical_repo import LogicalRepository
from core.canonizer import CanonizerService
from core.similarity import SimilarityManager

# Threads that did not stop in time; kept referenced until they end on their own.
_detached_threads: set = set()


def stop_thread(thread: Optional[QThread], wait_ms: int = 2000) -> bool:
    """
    Asks a worker thread to stop (cancel() or stop()) and waits for it.

    A thread that does not end within wait_ms is never terminated (that can leave
    locks or the database inconsistent); it stays referenced until it ends.

    Returns:
        True if the thread is no longer running.
    """
    if thread is None:
        return True
    for method in ("cancel", "stop"):
        if hasattr(thread, method):
            getattr(thread, method)()
            break
    if not thread.isRunning() or thread.wait(wait_ms):
        return True
    logger.warning(f"{type(thread).__name__} did not stop within {wait_ms} ms; letting it finish.")
    _detached_threads.add(thread)
    timer = QTimer()
    timer.setInterval(500)

    def release() -> None:
        # The owner may already have deleted the finished thread (deleteLater on QThread.finished)
        if sip.isdeleted(thread) or not thread.isRunning():
            timer.stop()
            _detached_threads.discard(thread)
    timer.timeout.connect(release)
    timer.start()
    thread._release_timer = timer  # keep the timer alive with the thread
    return False

class FunctionWorker(QThread):
    """Runs one blocking call (network, engine) off the GUI thread."""
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)  # the exception

    def __init__(self, function: Any) -> None:
        super().__init__()
        self._function = function

    def run(self) -> None:
        try:
            self.succeeded.emit(self._function())
        except Exception as e:  # handed to the GUI thread, which reports it
            self.failed.emit(e)


class BatchTaggingWorker(QThread):
    """
    Phase 106: Worker thread to apply tagging rules to many documents in background.
    """
    progress = pyqtSignal(int, int) # processed, total
    finished = pyqtSignal(int) # count of modified documents

    def __init__(self, db, filter_tree, rules=None, uuids=None) -> None:
        super().__init__()
        self.db = db
        self.filter_tree = filter_tree
        self.rules = rules # If None, will fetch enabled rules from Tree. Can be a single Rule.
        self.uuids = uuids # If None, will fetch all non-deleted documents
        self.is_cancelled = False

    def run(self) -> None:
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
            uuids = self.db.get_all_active_uuids()

        total = len(uuids)

        modified_count = 0
        try:
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
        except Exception as e:  # never leave the progress dialog waiting
            logger.error(f"Batch tagging failed: {e}", exc_info=True)
        finally:
            self.finished.emit(modified_count)

    def cancel(self) -> None:
        self.is_cancelled = True

class ImportWorker(QThread):
    """
    Worker thread to import documents in the background.
    """
    progress = pyqtSignal(int, str) # current_index, current_description
    finished = pyqtSignal(int, int, list, str) # success_count, total_count, imported_uuids, error_msg
    document_imported = pyqtSignal(str) # Emitted for each successfully created logical doc (UUID)

    def __init__(self, pipeline: PipelineProcessor, items: list, move_source: bool = False) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.items = items # List of (path, instructions) tuples
        self.move_source = move_source
        self.is_cancelled = False

    def run(self) -> None:
        success_count = 0
        imported_uuids = []

        self.pipeline.reset_cancellation()

        # Calculate effective total for progress reporting
        effective_total = 0
        for item in self.items:
            if isinstance(item, tuple) and item[0] == "BATCH" and isinstance(item[1], list):
                # For batch, we consider both ingestion and instruction steps later
                unique_files = set()
                for doc_instr in item[1]:
                    for pg in doc_instr.get("pages", []):
                        if "file_path" in pg:
                            unique_files.add(pg["file_path"])
                effective_total += len(unique_files) + len(item[1])
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
                    def batch_progress_cb(curr, total, label) -> None:
                        self.progress.emit(curr - 1, label)

                    def batch_entity_cb(uid) -> None:
                        self.document_imported.emit(uid)

                    try:
                        all_paths = set()
                        for doc_instr in instructions:
                            for pg in doc_instr.get("pages", []):
                                if "file_path" in pg:
                                    all_paths.add(pg["file_path"])

                        uuids = self.pipeline.process_batch_with_instructions(
                            list(all_paths),
                            instructions,
                            move_source=self.move_source,
                            progress_callback=batch_progress_cb,
                            entity_callback=batch_entity_cb
                        )
                        if uuids:
                            success_count += len(uuids)
                            imported_uuids.extend(uuids)
                            # current_global_idx is handled by the batch_progress_cb for UI
                            current_global_idx += (len(all_paths) + len(instructions))
                    except CancelledError:
                        logger.info("[ImportWorker] Batch import cancelled by user.")
                        break
                    except Exception as e:
                        logger.error(f"Batch Import Error: {e}")
                    continue

                self.progress.emit(current_global_idx, fpath)

                try:
                    if instructions:
                        # Pre-Flight Instruction Mode (Single File)
                        uuids = self.pipeline.process_document_with_instructions(
                            fpath,
                            instructions,
                            move_source=self.move_source,
                            entity_callback=lambda uid: self.document_imported.emit(uid)
                        )
                        if uuids:
                            success_count += len(uuids)
                            imported_uuids.extend(uuids)
                    else:
                        # Legacy Default Mode
                        doc = self.pipeline.process_document(fpath, move_source=self.move_source, skip_ai=True)
                        if doc:
                            self.document_imported.emit(doc.uuid)
                            success_count += 1
                            imported_uuids.append(doc.uuid)

                    current_global_idx += 1

                except CancelledError:
                    logger.info(f"[ImportWorker] Import of {fpath} cancelled by user.")
                    break
                except Exception as e:
                    logger.error(f"Error importing {fpath}: {e}")
                    current_global_idx += 1

            self.finished.emit(success_count, effective_total, imported_uuids, "")

        except CancelledError:
            logger.info("[ImportWorker] Import cancelled by user (outer).")
            self.finished.emit(success_count, effective_total, imported_uuids, "")
        except Exception as e:
            traceback.print_exc()
            self.finished.emit(success_count, effective_total, [], str(e))

    def cancel(self) -> None:
        self.is_cancelled = True
        self.pipeline.terminate_activity()

class ReprocessWorker(QThread):
    """
    Worker thread to reprocess documents in the background.
    """
    progress = pyqtSignal(int, str) # current_index, uuid/status
    finished = pyqtSignal(int, int, list) # success_count, total, processed_uuids
    error = pyqtSignal(str, str) # uuid, error_message

    def __init__(self, pipeline: PipelineProcessor, uuids: list[str], force_ocr: bool = False) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.uuids = uuids
        self.force_ocr = force_ocr
        self.is_cancelled = False

    def run(self) -> None:
        success_count = 0
        total = len(self.uuids)
        processed_uuids = []

        self.pipeline.reset_cancellation()

        try:
            for i, uuid in enumerate(self.uuids):
                if self.is_cancelled:
                    break

                self.progress.emit(i, uuid)

                try:
                    # Async Reprocess: Skip AI initially (Local Extraction only)
                    doc = self.pipeline.reprocess_document(uuid, skip_ai=True, force_ocr=self.force_ocr)
                    if doc:
                        success_count += 1
                        processed_uuids.append(uuid)
                    else:
                        self.error.emit(uuid, "Document skip or logic error (returned None)")
                except CancelledError:
                    logger.info(f"[ReprocessWorker] Reprocessing of {uuid} cancelled by user.")
                    break
                except Exception as e:
                    err_msg = str(e)
                    logger.error(f"Error reprocessing {uuid}: {err_msg}")
                    self.error.emit(uuid, err_msg)

            self.finished.emit(success_count, total, processed_uuids)

        except CancelledError:
            logger.info("[ReprocessWorker] Reprocessing cancelled by user (outer).")
            self.finished.emit(success_count, total, processed_uuids)
        except Exception as e:
            err_msg = f"Fatal Worker Error: {e}"
            traceback.print_exc()
            self.error.emit("worker", err_msg)
            self.finished.emit(success_count, total, [])

    def cancel(self) -> None:
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

    def __init__(self, pipeline: PipelineProcessor, filter_tree) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.filter_tree = filter_tree
        self.is_running = True
        self.is_paused = False

        self.canonizer = CanonizerService(pipeline.db,
                                        filter_tree=self.filter_tree,
                                        physical_repo=pipeline.physical_repo,
                                        logical_repo=pipeline.logical_repo)

    def run(self) -> None:
        logger.info("[MainLoop] Worker started.")
        self.canonizer.release_interrupted_documents()
        while self.is_running:
            if self.is_paused:
                self.status_changed.emit(self.tr("Paused"))
                time.sleep(0.5)
                continue

            try:
                # 1. Count pending items for progress reporting
                total_pending = self.pipeline.db.get_pending_pipeline_count()

                # If nothing to do, wait and continue
                if total_pending == 0:
                    self.status_changed.emit(self.tr("Idle"))
                    self.progress.emit(0, 0)
                else:
                    self.status_changed.emit(self.tr("Processing (%n remaining)", "", total_pending))
                    
                    # Track batch progress for the UI burst
                    burst_total = min(5, total_pending)
                    processed_in_this_run = 0

                    while processed_in_this_run < burst_total:
                        if not self.is_running:
                            logger.debug("[MainLoop] Stop requested mid-batch.")
                            break
                        if self.is_paused:
                            logger.debug("[MainLoop] Pause requested mid-batch.")
                            self.status_changed.emit(self.tr("Finishing current & pausing..."))
                            break

                        # Up to N engine calls run concurrently; all DB access stays in this thread.
                        parallel = max(1, min(burst_total - processed_in_this_run,
                                              self.canonizer.config.get_analysis_concurrency()))
                        processed_count = self.canonizer.process_pending_documents(limit=parallel, max_parallel=parallel)
                        if processed_count == 0:
                            break
                        
                        processed_in_this_run += processed_count
                        total_pending -= processed_count
                        # Emit (processed_so_far, total_in_this_burst)
                        self.progress.emit(processed_in_this_run, burst_total)
                        self.status_changed.emit(self.tr("Processing (%n remaining)", "", total_pending))
                        self.documents_processed.emit()

            except Exception as e:
                error_details = traceback.format_exc()
                logger.error(f"[MainLoop] FATAL ERROR: {e}\n{error_details}")
                self.fatal_error.emit("Background Pipeline Error", f"A fatal error occurred in the processing pipeline:\n\n{e}")
                self.is_running = False
                break

            # Sleep until next check
            for _ in range(50): 
                if not self.is_running or self.is_paused: break
                time.sleep(0.1)
        
        logger.info("[MainLoop] Worker stopped.")
        self.status_changed.emit(self.tr("Stopped"))

    def set_paused(self, paused: bool) -> None:
        self.is_paused = paused
        state = "PAUSED" if paused else "RESUMED"
        logger.info(f"[MainLoop] {state} requested.")
        if paused:
            self.status_changed.emit(self.tr("Finishing current & pausing..."))
        else:
             self.status_changed.emit(self.tr("Resuming..."))

        self.pause_state_changed.emit(paused)

    def stop(self) -> None:
        logger.info("[MainLoop] STOP requested.")
        self.status_changed.emit(self.tr("Stopping (finishing current)..."))
        self.is_running = False
        self.is_paused = False

class SimilarityWorker(QThread):
    """
    Worker thread to calculate document similarities in the background.
    """
    progress = pyqtSignal(int, int) # processed, total
    finished = pyqtSignal(list)      # list of duplicates

    class _Cancelled(Exception):
        """Raised from the progress callback to leave the comparison loop."""

    def __init__(self, db_manager, vault, threshold=0.85) -> None:
        super().__init__()
        self.sim_manager = SimilarityManager(db_manager, vault)
        self.threshold = threshold
        self.is_cancelled = False

    def cancel(self) -> None:
        """Stops the comparison at the next progress step."""
        self.is_cancelled = True

    def run(self) -> None:
        try:
            duplicates = self.sim_manager.find_duplicates(
                threshold=self.threshold,
                progress_callback=self._on_progress
            )
            self.finished.emit(duplicates)
        except self._Cancelled:
            logger.info("Similarity search cancelled.")
            self.finished.emit([])
        except Exception as e:
            logger.error(f"Similarity Worker Error: {e}", exc_info=True)
            self.finished.emit([])

    def _on_progress(self, current, total) -> None:
        if self.is_cancelled:
            raise self._Cancelled()
        self.progress.emit(current, total)

class MatchAnalysisWorker(QThread):
    """
    Heavy lifting for PDF comparison (Alignment, CV2, Overlays) in background.
    """
    finished = pyqtSignal(str) # temp_pdf_path
    error = pyqtSignal(str)

    def __init__(
        self, 
        left_path: str, 
        right_path: str, 
        engine: Any, 
        parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self.left_path = left_path
        self.right_path = right_path
        self.engine = engine
        self.is_cancelled = False

    def run(self) -> None:
        thread_id = int(QThread.currentThreadId())
        logger.info(f"[MatchAnalysisThread-{thread_id}] Started.")

        try:
            m_doc_native = fitz.open(self.left_path)
            m_doc_scan = fitz.open(self.right_path)
            
            diff_pdf = fitz.open()
            num_pages = m_doc_native.page_count
            
            logger.info(f"[MatchAnalysis] Background Pre-calculating {num_pages} pages...")
            
            for i in range(num_pages):
                if self.is_cancelled:
                    logger.info(f"[MatchAnalysisThread-{thread_id}] Cancellation detected at page {i+1}")
                    break
                    
                p_rect = m_doc_native[i].rect
                page = diff_pdf.new_page(width=p_rect.width, height=p_rect.height)
                
                logger.info(f"[MatchAnalysisThread-{thread_id}] Processing page {i+1}/{num_pages}...")
                
                # Render (lower DPI for speed? Using 130 for now)
                img_native = self.engine.pdf_page_to_numpy(m_doc_native, i, dpi=130)
                scan_idx = min(i, m_doc_scan.page_count - 1)
                img_scan = self.engine.pdf_page_to_numpy(m_doc_scan, scan_idx, dpi=130)
                
                aligned_scan, _ = self.engine.align_and_compare(img_native, img_scan)
                diff_overlay = self.engine.create_diff_overlay(img_native, aligned_scan)
                
                is_success, buffer = cv2.imencode(".png", diff_overlay)
                if is_success:
                    page.insert_image(p_rect, stream=buffer.tobytes())

            if self.is_cancelled: 
                logger.info(f"[MatchAnalysisThread-{thread_id}] Safely exiting loop before save.")
                return

            logger.info(f"[MatchAnalysisThread-{thread_id}] Saving result to temp folder...")
            fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix="diff_precalc_")
            os.close(fd)
            diff_pdf.save(temp_path)
            diff_pdf.close()
            m_doc_native.close()
            m_doc_scan.close()
            
            if not self.is_cancelled:
                logger.info(f"[MatchAnalysisThread-{thread_id}] Finished successfully. Emitting signal.")
                self.finished.emit(temp_path)
        except Exception as e:
            if not self.is_cancelled:
                logger.info(f"[MatchAnalysisThread-{thread_id}] Error: {e}")
                self.error.emit(str(e))
        finally:
            logger.info(f"[MatchAnalysisThread-{thread_id}] Cleanup starting...")
            try:
                if 'diff_pdf' in locals():
                    diff_pdf.close()
                if 'm_doc_native' in locals():
                    m_doc_native.close()
                if 'm_doc_scan' in locals():
                    m_doc_scan.close()
            except Exception as e:
                get_silent_logger().debug(f"Resource closure failed during cleanup: {e}")
            logger.info(f"[MatchAnalysisThread-{thread_id}] Cleanup complete. Thread record ending.")

    def cancel(self) -> None:
        """Requests the worker to stop immediately."""
        self.is_cancelled = True

class SemanticRenderingWorker(QThread):
    """
    Background worker to generate a high-quality PDF report from semantic data.
    Prevents UI freeze during ProfessionalPdfRenderer usage.
    """
    finished = pyqtSignal(str) # temp_pdf_path
    error = pyqtSignal(str)

    def __init__(self, semantic_data: Any, out_path: str, locale: str = "de", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.semantic_data = semantic_data
        self.out_path = out_path
        self.locale = locale

    def run(self) -> None:
        try:
            from core.pdf_renderer import ProfessionalPdfRenderer
            renderer = ProfessionalPdfRenderer(self.out_path, locale=self.locale)
            renderer.render_document(self.semantic_data)
            self.finished.emit(self.out_path)
        except Exception as e:
            logger.error(f"[SemanticRenderingWorker] Failed: {e}")
            self.error.emit(str(e))
