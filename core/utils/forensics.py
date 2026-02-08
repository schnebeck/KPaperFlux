
import fitz
import os

def check_pdf_immutable(file_path: str) -> bool:
    """
    Checks if a PDF document should be treated as immutable.
    Criteria:
    - Digital Signatures present.
    - Custom metadata 'kpaperflux_immutable' is 'true'.
    """
    if not os.path.exists(file_path) or not file_path.lower().endswith(".pdf"):
        return False
        
    try:
        doc = fitz.open(file_path)
        
        # 1. Check Metadata (Keywords field is the official storage)
        meta = doc.metadata
        if meta:
            keywords = meta.get("keywords", "")
            if keywords and "kpaperflux_immutable" in keywords:
                doc.close()
                return True
            
        # 2. Check Signatures
        # sig_flags returns a bitmask. 1 = contains signatures, 2 = contains XFA forms
        if doc.get_sig_flags() > 0:
            doc.close()
            return True
            
        doc.close()
    except Exception as e:
        print(f"[Forensics] Error checking PDF immutability for {file_path}: {e}")
        
    return False
