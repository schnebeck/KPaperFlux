from PyQt6.QtCore import QThread, pyqtSignal
from core.pipeline import PipelineProcessor
import traceback

class ImportWorker(QThread):
    """
    Worker thread to import documents in the background.
    """
    progress = pyqtSignal(int, str) # current_index, current_filename
    finished = pyqtSignal(int, int, str) # success_count, total_count, error_msg (if critical)
    
    def __init__(self, pipeline: PipelineProcessor, files: list[str], move_source: bool = False):
        super().__init__()
        self.pipeline = pipeline
        self.files = files
        self.move_source = move_source
        self.is_cancelled = False
        
    def run(self):
        success_count = 0
        total = len(self.files)
        
        try:
            for i, fpath in enumerate(self.files):
                if self.is_cancelled:
                    break
                    
                self.progress.emit(i, fpath)
                
                try:
                    self.pipeline.process_document(fpath, move_source=self.move_source)
                    success_count += 1
                except Exception as e:
                    print(f"Error importing {fpath}: {e}")
                    traceback.print_exc()
            
            self.finished.emit(success_count, total, "")
            
        except Exception as e:
            traceback.print_exc()
            self.finished.emit(success_count, total, str(e))
            
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
                    doc = self.pipeline.reprocess_document(uuid)
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
