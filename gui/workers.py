from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from core.pipeline import PipelineProcessor
import traceback
import queue
import time
from core.document import Document
from core.ai_analyzer import AIAnalyzer

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
        total = len(self.items)
        imported_uuids = []
        
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
                    self.progress.emit(i, "Batch Processing...")
                    try:
                        # Extract all possible file paths from instructions
                        all_paths = set()
                        for doc_instr in instructions:
                            for pg in doc_instr.get("pages", []):
                                if "file_path" in pg:
                                    all_paths.add(pg["file_path"])
                        
                        uuids = self.pipeline.process_batch_with_instructions(list(all_paths), instructions, move_source=self.move_source)
                        if uuids:
                            success_count += 1 # We count the BATCH as 1 successful "import task"? Or by doc count?
                            # Usually 1 item in 'items' = 1 progress step. 
                            imported_uuids.extend(uuids)
                    except Exception as e:
                        print(f"Batch Import Error: {e}")
                    continue

                self.progress.emit(i, fpath)
                
                try:
                    # Async Import: Skip AI initially
                    if instructions:
                        # Pre-Flight Instruction Mode
                        uuids = self.pipeline.process_document_with_instructions(fpath, instructions, move_source=self.move_source)
                        if uuids:
                            success_count += 1
                            imported_uuids.extend(uuids)
                    else:
                        # Legacy Default Mode
                        doc = self.pipeline.process_document(fpath, move_source=self.move_source, skip_ai=True)
                        if doc:
                            success_count += 1
                            imported_uuids.append(doc.uuid)
                            
                except Exception as e:
                    print(f"Error importing {fpath}: {e}")
                    traceback.print_exc()
            
            self.finished.emit(success_count, total, imported_uuids, "")
            
        except Exception as e:
            traceback.print_exc()
            self.finished.emit(success_count, total, [], str(e))
            
    def cancel(self):
        self.is_cancelled = True

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

class AIQueueWorker(QThread):
    """
    Worker thread that continuously processes documents from a queue for AI Analysis.
    Decouples import from AI rate limits.
    """
    doc_updated = pyqtSignal(str, Document) # uuid, updated_doc
    status_changed = pyqtSignal(str) # "Idle", "Processing...", "Cooldown..."
    
    def __init__(self, pipeline: PipelineProcessor):
        super().__init__()
        self.pipeline = pipeline
        self.queue = queue.Queue() # Items: (uuid, file_path)
        self.is_running = True
        self.total_added = 0
        self.processed_count = 0
        
    def add_task(self, uuid: str):
        """Add a document to the AI processing queue."""
        self.queue.put(uuid)
        self.total_added += 1
        
    def run(self):
        while self.is_running:
            try:
                # Get with timeout to allow checking is_running
                try:
                    uuid = self.queue.get(timeout=1.0)
                except queue.Empty:
                    if self.queue.qsize() == 0:
                        self.status_changed.emit("AI: Idle")
                        # Reset counters on idle
                        self.total_added = 0
                        self.processed_count = 0
                    continue
                
                # Calculate Progress
                current_idx = self.processed_count + 1
                percent = int((current_idx / self.total_added) * 100) if self.total_added > 0 else 0
                
                delay = AIAnalyzer.get_adaptive_delay()
                # Format: "AI: Processing {uuid} (3/10 - 33%). Delay: {delay}s"
                msg = f"AI: Processing {uuid[:8]}... ({current_idx}/{self.total_added} - {percent}%)"
                
                if delay > 0:
                    msg += f", Delaytime: {delay:.1f}sec."
                    
                self.status_changed.emit(msg)
                
                # Fetch Doc
                doc = self.pipeline.db.get_document_by_uuid(uuid)
                if not doc:
                    self.queue.task_done()
                    continue
                    
                # We need the full path to generate images?
                # Pipeline._run_ai_analysis needs file_path optionally.
                # If path isn't stored in Doc properly (we have original_filename but not full path?)
                # We stored it in vault. Pipeline knows how to get it?
                # Pipeline doesn't have "get_path(uuid)".
                # But we can reconstruct it? Or just pass doc.
                # Wait, _run_ai_analysis takes (doc, file_path).
                # file_path is used for "Vision". 
                # If we don't have it, we skip vision.
                # We should try to find it in vault logic.
                # doc does not strictly store its current absolute path.
                # But pipeline.vault can search?
                # Let's try to pass None for now or improve.
                # Better: `pipeline.reprocess_document` logic fetches path?
                # Let's peek pipeline logic later. For now, pass None implies Text Only. 
                # Ideally we want Vision.
                # Actually `reprocess_document` finds the file. 
                # Let's use `pipeline._run_ai_analysis(doc, path)`
                
                # Find path
                # Vault has `get_document_path`? No.
                # Let's assume pipeline.vault.get_file_path(doc)?
                # We will check Vault API. simpler:
                from pathlib import Path
                # Heuristic: vault_path / doc.uuid + suffix?
                # Vault stores as {uuid}.pdf usually or with original name?
                # Vault behavior: store_document returns path.
                # Let's use `pipeline.vault.get_file_path(doc.uuid)`
                path = self.pipeline.vault.get_file_path(doc.uuid)
                
                # Run AI
                try:
                    self.pipeline._run_ai_analysis(doc, path)
                    
                    # Relaod updated Doc from DB (V2 Entity -> V1 DTO)
                    # Do NOT save the stale 'doc' back!
                    updated_doc = self.pipeline.db.get_document_by_uuid(uuid)
                    if updated_doc:
                        self.doc_updated.emit(uuid, updated_doc)
                        
                except Exception as e:
                    print(f"AI Queue Error {uuid}: {e}")
                
                self.processed_count += 1
                self.queue.task_done()
                
            except Exception as e:
                print(f"AI Worker Loop Error: {e}")
                time.sleep(1)

    def stop(self):
        self.is_running = False

class MainLoopWorker(QThread):
    """
    Intelligent Main Loop (Stage 1+).
    Periodically checks for READY_FOR_PIPELINE documents and processes them.
    Also manages Stage 2 Queue if needed.
    """
    status_changed = pyqtSignal(str)
    documents_processed = pyqtSignal() # Notify UI to refresh list
    
    def __init__(self, pipeline: PipelineProcessor):
        super().__init__()
        self.pipeline = pipeline
        self.is_running = True
        from core.canonizer import CanonizerService
        self.canonizer = CanonizerService(pipeline.db, 
                                        physical_repo=pipeline.physical_repo, 
                                        logical_repo=pipeline.logical_repo)

    def run(self):
        while self.is_running:
            try:
                # 1. Background Canonizing (Stage 1)
                # Check if any documents are READY_FOR_PIPELINE
                # limit 1 to avoid hogging the loop, or higher if batching
                processed_any = False
                
                # We use a shortcut to check counts first to avoid overhead?
                # For now just call and let it handle emptiness.
                
                self.canonizer.process_pending_documents(limit=5)
                # Note: process_pending_documents in canonizer.py returns nothing currently.
                # We should probably check if something changed.
                
                # Signal UI
                self.documents_processed.emit()
                
            except Exception as e:
                print(f"[MainLoop] Error: {e}")
                import traceback
                traceback.print_exc()
            
            # Sleep until next check (e.g. 5 seconds)
            for _ in range(50): # 5 seconds split for faster stop
                if not self.is_running: break
                time.sleep(0.1)

    def stop(self):
        self.is_running = False

class SimilarityWorker(QThread):
    """
    Worker thread to calculate document similarities in the background.
    """
    progress = pyqtSignal(int, int) # processed, total
    finished = pyqtSignal(list)      # list of duplicates

    def __init__(self, db_manager, vault, threshold=0.85):
        super().__init__()
        from core.similarity import SimilarityManager
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
