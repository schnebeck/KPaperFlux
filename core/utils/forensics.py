"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/utils/forensics.py
Version:        2.2.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Forensic analysis for PDFs. Detects digital signatures, 
                ZUGFeRD/Factur-X data, and immutability flags.
------------------------------------------------------------------------------
"""

import fitz
import os
from enum import Enum
from typing import Optional

class PDFClass(Enum):
    """Classification according to Hybrid Protection Standard."""
    STANDARD = "C"        # Standard Scan/PDF
    SIGNED = "A"          # Digitally Signed
    ZUGFERD = "B"         # ZUGFeRD/Factur-X XML embedded
    SIGNED_ZUGFERD = "AB" # Both Signed and ZUGFeRD
    HYBRID = "H"          # KPaperFlux Hybrid Container (Visual + Original inside)

def get_pdf_class(file_path: str) -> PDFClass:
    """
    Analyzes the structure of a PDF to determine its protection class.
    """
    if not os.path.exists(file_path) or not file_path.lower().endswith(".pdf"):
        return PDFClass.STANDARD
        
    try:
        doc = fitz.open(file_path)
        
        # 0. Detect Hybrid (KPaperFlux specific)
        meta = doc.metadata
        keywords = meta.get("keywords", "")
        is_hybrid = "kpaperflux_immutable" in keywords
        
        if not is_hybrid:
            # Check for specific attachment name as fallback
            for i in range(doc.embfile_count()):
                if doc.embfile_info(i)["name"] == "original_signed_source.pdf":
                    is_hybrid = True
                    break
        
        if is_hybrid:
            doc.close()
            return PDFClass.HYBRID

        # 1. Detect Signatures
        sig_flags = 0
        if hasattr(doc, "get_sigflags"): 
            sig_flags = doc.get_sigflags()
        elif hasattr(doc, "sig_flags"): 
            sig_flags = doc.sig_flags
        elif hasattr(doc, "getSigFlags"): 
            sig_flags = doc.getSigFlags()
            
        has_signature = (sig_flags > 0)
        
        # 2. Detect ZUGFeRD
        has_zugferd = False
        for i in range(doc.embfile_count()):
            name = doc.embfile_info(i)["name"]
            if name.lower() in ["factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml"]:
                has_zugferd = True
                break
                
        doc.close()
        
        if has_signature and has_zugferd:
            return PDFClass.SIGNED_ZUGFERD
        if has_signature:
            return PDFClass.SIGNED
        if has_zugferd:
            return PDFClass.ZUGFERD
            
    except Exception as e:
        print(f"[Forensics] Error analyzing PDF class for {file_path}: {e}")
        
    return PDFClass.STANDARD

def check_pdf_immutable(file_path: str) -> bool:
    """
    Legacy wrapper for immutability check.
    Returns True for Class A, AB, or if kpaperflux_immutable flag is set.
    """
    p_class = get_pdf_class(file_path)
    if p_class in [PDFClass.SIGNED, PDFClass.SIGNED_ZUGFERD]:
        return True
        
    # Check for manual metadata flag
    try:
        doc = fitz.open(file_path)
        meta = doc.metadata
        if meta:
            keywords = meta.get("keywords", "")
            if keywords and "kpaperflux_immutable" in keywords:
                doc.close()
                return True
        doc.close()
    except:
        pass
        
    return False
