
from typing import List, Tuple, Dict, Set
from core.database import DatabaseManager
from core.document import Document
import difflib

class SimilarityManager:
    """
    Identifies potential duplicate documents based on metadata and text content.
    """
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def find_duplicates(self, threshold: float = 0.85) -> List[Tuple[Document, Document, float]]:
        """
        Find pairs of documents that are likely duplicates.
        Returns a list of tuples: (doc_a, doc_b, similarity_score).
        """
        documents = self.db_manager.get_all_documents()
        duplicates = []
        
        # Optimization: Filter by obvious non-matches?
        # For now, simplistic O(N^2) for small datasets is acceptable.
        # To optimize, we could group by Amount or Date.
        
        # In a real app with many docs, we'd use LSH or similar.
        # Here, we compare every pair but skip redundant (A,B) vs (B,A).
        
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
        Weighted average of Text Similarity and Metadata Match.
        """
        # 1. Metadata Hard Check
        # If Amount and Date are present and identical, that's a strong sign.
        metadata_score = 0.0
        if doc_a.amount is not None and doc_b.amount is not None:
             if doc_a.amount == doc_b.amount:
                 metadata_score += 0.3
        
        if doc_a.doc_date and doc_b.doc_date:
            if doc_a.doc_date == doc_b.doc_date:
                metadata_score += 0.2
                
        # 2. Text Similarity (Jaccard)
        # Jaccard is faster than SequenceMatcher for full text
        text_a = (doc_a.text_content or "").lower().split()
        text_b = (doc_b.text_content or "").lower().split()
        
        if not text_a or not text_b:
            return metadata_score # Fallback if no text
            
        set_a = set(text_a)
        set_b = set(text_b)
        
        if not set_a or not set_b:
             jaccard = 0.0
        else:
             intersection = len(set_a & set_b)
             union = len(set_a | set_b)
             jaccard = intersection / union
        
        # Weighted Score
        # If metadata matches perfectly (0.5), Jaccard only needs to be moderate.
        # If metadata missing, Jaccard needs to be high.
        
        # Let's say Text is the primary driver (0.5 to 1.0).
        # Actually SequenceMatcher is significantly better for OCR text where characters might slightly differ.
        # But Jaccard on tokens is robust enough for "Duplicate" check.
        
        # Let's just return Jaccard if metadata is weak, or boosted Jaccard if metadata matches.
        
        final_score = jaccard
        if metadata_score >= 0.5: # Both Amount and Date match
            # Boost score, because it's very likely a duplicate if text is even remotely similar
            final_score += 0.2
            if final_score > 1.0: final_score = 1.0
            
        return final_score

