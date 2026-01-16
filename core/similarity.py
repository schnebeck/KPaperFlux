
from typing import List, Tuple, Dict, Set
from core.database import DatabaseManager
from core.document import Document
import difflib
import math
from pathlib import Path
from pdf2image import convert_from_path
from PIL import Image, ImageChops, ImageStat
import os


class SimilarityManager:
    """
    Identifies potential duplicate documents based on metadata, text content, and visual appearance.
    """
    def __init__(self, db_manager: DatabaseManager, vault=None):
        self.db_manager = db_manager
        self.vault = vault # Needed to resolve file paths
        self.thumbnail_cache = {} # Map uuid -> PIL.Image

    def find_duplicates(self, threshold: float = 0.85) -> List[Tuple[Document, Document, float]]:
        """
        Find pairs of documents that are likely duplicates.
        Returns a list of tuples: (doc_a, doc_b, similarity_score).
        """
        documents = self.db_manager.get_all_documents()
        duplicates = []
        self.thumbnail_cache = {} # Clear cache
        
        n = len(documents)
        for i in range(n):
            for j in range(i + 1, n):
                doc_a = documents[i]
                doc_b = documents[j]
                
                score = self.calculate_similarity(doc_a, doc_b)
                if score >= threshold:
                    duplicates.append((doc_a, doc_b, score))
                    
        return duplicates

    def calculate_similarity(self, doc_a: Document, doc_b: Document) -> float:
        """
        Calculate a similarity score between 0.0 and 1.0.
        Max of (Text Jaccard, Visual Similarity) boosted by Metadata.
        """
        # Critical Metadata Check (Veto Power)
        # If dates are present and differ, these are likely different monthly invoices (same template).
        if doc_a.doc_date and doc_b.doc_date and doc_a.doc_date != doc_b.doc_date:
            return 0.0 # Strongly reject different dates
            
        # If amounts are present and differ significanly, likely different files.
        if doc_a.amount is not None and doc_b.amount is not None and doc_a.amount != doc_b.amount:
            # Allow small float tolerance? Assuming exact match needed for duplicates.
            return 0.1 # Very low score
            
        # Metadata Score (Boost)
        metadata_score = 0.0
        if doc_a.amount is not None and doc_b.amount is not None and doc_a.amount == doc_b.amount:
             metadata_score += 0.3
        if doc_a.doc_date and doc_b.doc_date and doc_a.doc_date == doc_b.doc_date:
                metadata_score += 0.2
                
        # Text Similarity (Jaccard)
        text_a = (doc_a.text_content or "").lower().split()
        text_b = (doc_b.text_content or "").lower().split()
        
        if not text_a or not text_b:
             text_score = 0.0
        else:
             set_a = set(text_a)
             set_b = set(text_b)
             if not set_a or not set_b:
                 text_score = 0.0
             else:
                 text_score = len(set_a & set_b) / len(set_a | set_b)
        
        # Visual Similarity
        visual_score = 0.0
        if self.vault:
            visual_score = self.calculate_visual_similarity(doc_a, doc_b)
            
        # Strategy:
        # If visual score is high (e.g. > 0.9), it's likely a scan of the same doc, even if text failed.
        # If text score is high, it's a match.
        # Take the maximum of Text and Visual as the base content score.
        
        content_score = max(text_score, visual_score)
        
        final_score = content_score
        
        # Boost if metadata matches
        if metadata_score >= 0.5:
            final_score += 0.2
            
        return min(final_score, 1.0)

    def calculate_visual_similarity(self, doc_a: Document, doc_b: Document) -> float:
        """
        Render pages as low-res images and compare.
        Supports checking if a single-page doc is contained in a multi-page doc.
        Returns 0.0 to 1.0 (1.0 = identical).
        """
        imgs_a = self._get_cached_thumbnails(doc_a)
        imgs_b = self._get_cached_thumbnails(doc_b)
        
        if not imgs_a or not imgs_b:
            return 0.0
            
        # Strategy:
        # Case 1: Both single page -> simple compare.
        # Case 2: One is single page, other multi -> Check for containment (Max Match).
        # Case 3: Both multi -> Compare P1 vs P1 (Assumption: First page usually identifies doc).
        
        best_sim = 0.0
        
        if len(imgs_a) == 1 and len(imgs_b) > 1:
            # Check if A is in B
            for img_b in imgs_b:
                sim = self._compare_images(imgs_a[0], img_b)
                if sim > best_sim: best_sim = sim
            return best_sim
            
        elif len(imgs_b) == 1 and len(imgs_a) > 1:
             # Check if B is in A
            for img_a in imgs_a:
                sim = self._compare_images(img_a, imgs_b[0])
                if sim > best_sim: best_sim = sim
            return best_sim
            
        else:
            # P1 vs P1
            return self._compare_images(imgs_a[0], imgs_b[0])

    def _compare_images(self, img_a: Image.Image, img_b: Image.Image) -> float:
        """Compare two PIL images using RMS."""
        if img_a.size != img_b.size:
             # Resize secondary to primary
             img_b = img_b.resize(img_a.size)
             
        diff = ImageChops.difference(img_a, img_b)
        h = diff.histogram()
        sq = (value * ((idx % 256) ** 2) for idx, value in enumerate(h))
        sum_of_squares = sum(sq)
        rms = math.sqrt(sum_of_squares / float(img_a.size[0] * img_a.size[1]))
        
        # Heuristic normalization
        sim = max(0.0, 1.0 - (rms / 100.0))
        return sim

    def _get_cached_thumbnails(self, doc: Document) -> List[Image.Image]:
        """Return list of thumbnails for up to first 5 pages, ignoring KPaperFlux stamps."""
        if doc.uuid in self.thumbnail_cache:
            return self.thumbnail_cache[doc.uuid]
            
        path_str = self.vault.get_file_path(doc.uuid)
        if not path_str:
            return []
            
        path = Path(path_str)
        if not path.exists():
            return []
            
        # Check for stamps and create clean temp if needed
        render_path = path
        temp_file = None
        
        try:
            from core.stamper import DocumentStamper
            import tempfile
            import shutil
            
            stamper = DocumentStamper()
            if stamper.has_stamp(str(path)):
                # Create temp file
                fd, temp_path = tempfile.mkstemp(suffix=".pdf")
                os.close(fd)
                shutil.copy2(path, temp_path)
                
                # Check stamps on temp (same as original)
                # Remove all stamps
                if stamper.remove_stamp(temp_path):
                    render_path = Path(temp_path)
                    temp_file = temp_path
                else:
                    # Failed to strip or no stamps found? Use temp anyway or original?
                    pass
        except Exception as e:
            print(f"Error checking/stripping stamps for {doc.original_filename}: {e}")
            
        try:
            # Render first 5 pages, Size 128px
            images = convert_from_path(str(render_path), first_page=1, last_page=5, size=128, grayscale=True)
            thumbnails = []
            for img in images:
                # Resize to fixed 64x80
                thumb = img.resize((64, 80))
                thumbnails.append(thumb)
                
            self.thumbnail_cache[doc.uuid] = thumbnails
            
            # Cleanup temp
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)
                
            return thumbnails
            
        except Exception as e:
            print(f"Visual Sim Error {doc.original_filename}: {e}")
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)
            
        return []

