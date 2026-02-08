
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
        # PyMuPDF API changed names across versions (v1.14 -> v1.24+).
        # We check multiple variants to ensure compatibility across distributions.
        sig_flags = 0
        if hasattr(doc, "get_sigflags"): 
            # Modern PEP8 style (Note: get_sigflags NOT get_sig_flags)
            sig_flags = doc.get_sigflags()
        elif hasattr(doc, "sig_flags"): 
            # Upcoming property-based API in v2+
            sig_flags = doc.sig_flags
        elif hasattr(doc, "getSigFlags"): 
            # Legacy CamelCase style (Common in v1.18 and older)
            sig_flags = doc.getSigFlags()
            
        if sig_flags > 0:
            doc.close()
            return True
            
        doc.close()
    except Exception as e:
        print(f"[Forensics] Error checking PDF immutability for {file_path}: {e}")
        
    return False
