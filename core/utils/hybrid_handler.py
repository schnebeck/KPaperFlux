"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/utils/hybrid_handler.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Handles the creation and maintenance of hybrid PDF containers
                according to the Hybrid Protection Standard.
------------------------------------------------------------------------------
"""

import fitz
import os
import io
from typing import Optional
from core.utils.forensics import get_pdf_class, PDFClass

def prepare_hybrid_container(file_path: str, output_path: str) -> bool:
    """
    Implements the Hybrid Protection Standard for Class A, B, and AB.
    """
    p_class = get_pdf_class(file_path)
    
    if p_class == PDFClass.STANDARD or p_class == PDFClass.HYBRID:
        return False # No handling needed or already hybrid
        
    if p_class in [PDFClass.SIGNED, PDFClass.SIGNED_ZUGFERD]:
        # Class A / AB: Envelope Strategy
        return _create_envelope(file_path, output_path, p_class)
    
    if p_class == PDFClass.ZUGFERD:
        # Class B: Extraction/Re-Embedding Strategy
        # Note: This is usually called AFTER a modification like stamping.
        # But we can also use it to create a "working copy" that is clean.
        return _create_zugferd_working_copy(file_path, output_path)
        
    return False

def _create_envelope(original_path: str, output_path: str, p_class: PDFClass) -> bool:
    """
    Class A/AB: Renders pages as images and embeds the original.
    """
    try:
        doc_orig = fitz.open(original_path)
        doc_new = fitz.open()
        
        # 1. Visual Rendition (Image-based)
        for i in range(doc_orig.page_count):
            page = doc_orig[i]
            # DPI 150 is a good trade-off between quality and size for DMS
            pix = page.get_pixmap(dpi=150) 
            img_page = doc_new.new_page(width=page.rect.width, height=page.rect.height)
            img_page.insert_image(page.rect, pixmap=pix)
            
        # 2. Embed Original PDF
        with open(original_path, "rb") as f:
            orig_data = f.read()
        doc_new.embfile_add(
            "original_signed_source.pdf", 
            orig_data, 
            filename="original_signed_source.pdf", 
            desc="Original Digitally Signed Document (Audit Trail)"
        )
        
        # 3. For Class AB: Extract and also embed XML separately (Compatibility Layer)
        if p_class == PDFClass.SIGNED_ZUGFERD:
            for i in range(doc_orig.embfile_count()):
                info = doc_orig.embfile_info(i)
                name = info["name"].lower()
                if name in ["factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml"]:
                    xml_data = doc_orig.embfile_get(i)
                    doc_new.embfile_add(
                        info["name"], 
                        xml_data, 
                        filename=info["name"], 
                        desc="ZUGFeRD/Factur-X Structured Data"
                    )
                    break
        
        # 4. Mark as KPaperFlux Hybrid in Metadata
        meta = doc_new.metadata
        keywords = meta.get("keywords", "")
        if "kpaperflux_immutable" not in keywords:
            keywords = f"{keywords} kpaperflux_immutable".strip()
        doc_new.set_metadata({**meta, "keywords": keywords, "subject": "KPaperFlux Hybrid Container"})
        
        doc_new.save(output_path)
        doc_new.close()
        doc_orig.close()
        return True
    except Exception as e:
        print(f"[HybridHandler] Error creating envelope: {e}")
        return False

def _create_zugferd_working_copy(original_path: str, output_path: str) -> bool:
    """
    Class B: Just a copy for now, but ensured to have all XMLs.
    """
    try:
        import shutil
        shutil.copy2(original_path, output_path)
        return True
    except Exception as e:
        print(f"[HybridHandler] Error creating Class B working copy: {e}")
        return False

def restore_zugferd_xml(original_source_path: str, target_pdf_path: str) -> bool:
    """
    Extracts ZUGFeRD XML from original and re-embeds it into target.
    Used for Class B after stamping.
    """
    try:
        doc_orig = fitz.open(original_source_path)
        xml_data = None
        xml_name = "factur-x.xml"
        
        for i in range(doc_orig.embfile_count()):
            info = doc_orig.embfile_info(i)
            name = info["name"].lower()
            if name in ["factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml"]:
                xml_data = doc_orig.embfile_get(i)
                xml_name = info["name"]
                break
        
        doc_orig.close()
        
        if xml_data:
            doc_target = fitz.open(target_pdf_path)
            # Remove old ones if they exist
            for i in range(doc_target.embfile_count()):
                if doc_target.embfile_info(i)["name"].lower() == xml_name.lower():
                    doc_target.embfile_del(i)
                    break
            
            doc_target.embfile_add(xml_name, xml_data, filename=xml_name, desc="Restored ZUGFeRD Data")
            doc_target.save(target_pdf_path, incremental=True, encryption=0)
            doc_target.close()
            return True
            
        return False
    except Exception as e:
        print(f"[HybridHandler] Error restoring ZUGFeRD XML: {e}")
        return False
