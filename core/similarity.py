"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/similarity.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Similarity engine for identifying duplicate documents. Uses a 
                multi-modal approach combining metadata heuristics, text 
                Jaccard similarity, and visual RMS comparison.
------------------------------------------------------------------------------
"""

import math
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from pdf2image import convert_from_path
from PIL import Image, ImageChops

from core.database import DatabaseManager
from core.document import Document


class SimilarityManager:
    """
    Identifies potential duplicate documents based on metadata, text content, and visual appearance.
    """

    def __init__(self, db_manager: DatabaseManager, vault: Optional[Any] = None) -> None:
        """
        Initializes the SimilarityManager.

        Args:
            db_manager: The database manager for accessing document data.
            vault: The document vault for resolving file paths (optional).
        """
        self.db_manager: DatabaseManager = db_manager
        self.vault: Optional[Any] = vault  # Needed to resolve file paths
        self.thumbnail_cache: Dict[str, List[Image.Image]] = {}  # Map uuid -> List of PIL.Image

    def find_duplicates(self, threshold: float = 0.85, progress_callback: Optional[Callable[[int, int], None]] = None) -> List[Tuple[Document, Document, float]]:
        """
        Find pairs of documents that are likely duplicates.

        Args:
            threshold: Similarity score threshold (0.0 to 1.0) above which documents are considered duplicates.
            progress_callback: Optional function(current, total) for progress reporting.

        Returns:
            A list of tuples containing (doc_a, doc_b, similarity_score).
        """
        # Phase 102: Use Entity View instead of legacy get_all_documents
        documents = self.db_manager.get_all_entities_view()
        duplicates: List[Tuple[Document, Document, float]] = []
        self.thumbnail_cache = {}  # Clear cache for a fresh scan

        n = len(documents)
        total_pairs = (n * (n - 1)) // 2
        processed = 0

        for i in range(n):
            for j in range(i + 1, n):
                doc_a = documents[i]
                doc_b = documents[j]

                score = self.calculate_similarity(doc_a, doc_b)
                if score >= threshold:
                    duplicates.append((doc_a, doc_b, score))

                processed += 1
                if progress_callback:
                    progress_callback(processed, total_pairs)

        return duplicates

    def calculate_similarity(self, doc_a: Document, doc_b: Document) -> float:
        """
        Calculate a similarity score between 0.0 and 1.0.
        Combined logic of Text Jaccard and Visual Similarity, boosted by Metadata.

        Args:
            doc_a: First document to compare.
            doc_b: Second document to compare.

        Returns:
            A similarity score between 0.0 and 1.0.
        """
        # 1. Critical Metadata Check (Veto Power)
        # If dates are present and differ, these are likely different monthly invoices.
        if doc_a.doc_date and doc_b.doc_date and doc_a.doc_date != doc_b.doc_date:
            return 0.0

        # If amounts are present and differ significantly, likely different files.
        if doc_a.amount is not None and doc_b.amount is not None and doc_a.amount != doc_b.amount:
            return 0.1

        # 2. Base Metadata Score (Boost Factor)
        metadata_score = 0.0
        if doc_a.amount is not None and doc_b.amount is not None and doc_a.amount == doc_b.amount:
            metadata_score += 0.3
        if doc_a.doc_date and doc_b.doc_date and doc_a.doc_date == doc_b.doc_date:
            metadata_score += 0.2

        # 3. Text Similarity (Jaccard Index)
        text_a: List[str] = (doc_a.text_content or "").lower().split()
        text_b: List[str] = (doc_b.text_content or "").lower().split()

        if not text_a or not text_b:
            text_score = 0.0
        else:
            set_a: Set[str] = set(text_a)
            set_b: Set[str] = set(text_b)
            if not set_a or not set_b:
                text_score = 0.0
            else:
                text_score = len(set_a & set_b) / len(set_a | set_b)

        # 4. Visual Similarity
        visual_score = 0.0
        if self.vault:
            visual_score = self.calculate_visual_similarity(doc_a, doc_b)

        # 5. Combination Strategy
        # Use maximum of Text and Visual as base content score.
        content_score = max(text_score, visual_score)
        final_score = content_score

        # Boost if metadata matches
        if metadata_score >= 0.5:
            final_score += 0.2

        return min(final_score, 1.0)

    def calculate_visual_similarity(self, doc_a: Document, doc_b: Document) -> float:
        """
        Render pages as low-res images and compare them.
        Handles containment (single page in multi-page doc) and P1-to-P1 comparison.

        Args:
            doc_a: First document.
            doc_b: Second document.

        Returns:
            A visual similarity score between 0.0 and 1.0.
        """
        imgs_a = self._get_cached_thumbnails(doc_a)
        imgs_b = self._get_cached_thumbnails(doc_b)

        if not imgs_a or not imgs_b:
            return 0.0

        best_sim = 0.0

        # Case 1: A is single page, B is multi -> Check for containment
        if len(imgs_a) == 1 and len(imgs_b) > 1:
            for img_b in imgs_b:
                sim = self._compare_images(imgs_a[0], img_b)
                if sim > best_sim:
                    best_sim = sim
            return best_sim

        # Case 2: B is single page, A is multi -> Check for containment
        elif len(imgs_b) == 1 and len(imgs_a) > 1:
            for img_a in imgs_a:
                sim = self._compare_images(img_a, imgs_b[0])
                if sim > best_sim:
                    best_sim = sim
            return best_sim

        # Case 3: Both single or both multi -> Compare First Page
        else:
            return self._compare_images(imgs_a[0], imgs_b[0])

    def _compare_images(self, img_a: Image.Image, img_b: Image.Image) -> float:
        """
        Compare two images using Root Mean Square (RMS) of color difference.

        Args:
            img_a: First image.
            img_b: Second image.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        if img_a.size != img_b.size:
            img_b = img_b.resize(img_a.size)

        diff = ImageChops.difference(img_a, img_b)
        h = diff.histogram()
        sq = (value * ((idx % 256) ** 2) for idx, value in enumerate(h))
        sum_of_squares = sum(sq)
        rms = math.sqrt(sum_of_squares / float(img_a.size[0] * img_a.size[1]))

        # Normalize RMS: 0 (identical) to ~100+ (very different)
        sim = max(0.0, 1.0 - (rms / 100.0))
        return sim

    def _get_cached_thumbnails(self, doc: Document) -> List[Image.Image]:
        """
        Resolves, renders, and caches thumbnails for a document.
        Strips KPaperFlux stamps before rendering to ensure comparison robustness.

        Args:
            doc: The document to render.

        Returns:
            A list of PIL Image objects.
        """
        if doc.uuid in self.thumbnail_cache:
            return self.thumbnail_cache[doc.uuid]

        # Resolve path
        path_str = self.vault.get_file_path(doc.uuid)
        if not path_str or not os.path.exists(path_str):
            if hasattr(self.db_manager, "get_source_uuid_from_entity"):
                phys_uuid = self.db_manager.get_source_uuid_from_entity(doc.uuid)
                if phys_uuid:
                    path_str = self.vault.get_file_path(phys_uuid)

        if not path_str:
            return []

        path = Path(path_str)
        if not path.exists():
            return []

        render_path = path
        temp_file: Optional[str] = None

        # Phase 98: Strip stamps before comparison
        try:
            from core.stamper import DocumentStamper
            import shutil

            stamper = DocumentStamper()
            if stamper.has_stamp(str(path)):
                fd, temp_path = tempfile.mkstemp(suffix=".pdf")
                os.close(fd)
                shutil.copy2(path, temp_path)

                if stamper.remove_stamp(temp_path):
                    render_path = Path(temp_path)
                    temp_file = temp_path
        except (ImportError, IOError) as e:
            print(f"[Similarity] Error stripping stamps for {doc.original_filename}: {e}")

        try:
            # Render first 5 pages, low res (grayscale)
            images = convert_from_path(str(render_path), first_page=1, last_page=5, size=128, grayscale=True)
            thumbnails: List[Image.Image] = []
            for img in images:
                # Resize to standard aspect ratio/thumbnail size
                thumb = img.resize((64, 80))
                thumbnails.append(thumb)

            self.thumbnail_cache[doc.uuid] = thumbnails
            return thumbnails

        except Exception as e:
            print(f"[Similarity] Visual Sim Error {doc.original_filename}: {e}")
            return []
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass
