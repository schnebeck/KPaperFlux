
import os
import cv2
import fitz
import numpy as np
from pathlib import Path
from PyQt6.QtCore import QObject
from core.plugins.base import KPaperFluxPlugin
from core.utils.hybrid_engine import HybridEngine
from core.utils.forensics import check_pdf_immutable

class HybridAssemblerPlugin(KPaperFluxPlugin):
    """
    Plugin to assemble hybrid PDF files by combining native text layers
    with scanned signatures/stamps.
    """
    
    def __init__(self, api=None):
        super().__init__(api)
        self.dialog = None

    def get_name(self) -> str:
        return "Hybrid Assembler"

    def get_description(self) -> str:
        return "Assembles hybrid PDFs from native and scanned versions."

    def get_tool_actions(self, parent=None):
        from PyQt6.QtGui import QAction
        action = QAction("Assemble Hybrid PDFs...", parent)
        action.triggered.connect(lambda: self.open_matching_dialog(parent))
        return [action]

    def open_matching_dialog(self, parent=None):
        if not self.dialog:
            # Ensure local path is in sys.path for the import
            import sys
            plugin_dir = os.path.dirname(__file__)
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)
                
            from matching_dialog import MatchingDialog
            self.dialog = MatchingDialog(plugin=self, parent=parent)
            self.dialog.finished_closing.connect(self._on_dialog_closed)
        
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _on_dialog_closed(self):
        self.dialog = None

    def create_hybrid(self, native_pdf: str, scan_pdf: str, output_path: str) -> bool:
        """
        Logic for assembling the hybrid with minimal file size.
        - Uses the native PDF as the base (preserving vector text).
        - Extracts signatures/stamps from the scan as transparent overlays.
        - Overlays only the delta onto the native pages at 300 DPI.
        """
        try:
            doc_native = fitz.open(native_pdf)
            doc_scan = fitz.open(scan_pdf)
            
            engine = HybridEngine()

            for i in range(min(doc_native.page_count, doc_scan.page_count)):
                # 1. Render pages for analysis (300 DPI for high-fidelity extraction)
                img_native = engine.pdf_page_to_numpy(doc_native, i, dpi=300)
                img_scan_raw = engine.pdf_page_to_numpy(doc_scan, i, dpi=300)
                
                # 2. Align and Extract signatures/stamps only
                img_scan_aligned, _ = engine.align_and_compare(img_native, img_scan_raw)
                overlay_cv, pixel_count = engine.extract_high_fidelity_overlay(img_native, img_scan_aligned)

                if overlay_cv is not None and pixel_count > 100:
                    # 3. Create transparent PNG of the signatures
                    # Use Level 9 compression + alpha channel
                    success, buffer = cv2.imencode(".png", overlay_cv, [cv2.IMWRITE_PNG_COMPRESSION, 9])
                    if success:
                        img_bytes = buffer.tobytes()
                        # Overlay onto the original native page to keep vector text intact
                        page_native = doc_native[i]
                        page_native.insert_image(page_native.rect, stream=img_bytes)

            # 4. Metadata handling on the modified native doc
            standard_keys = ["title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate"]
            meta = {k: v for k, v in doc_native.metadata.items() if k in standard_keys}
            
            # Use 'keywords' to store our immutable flag (Standard compliant)
            current_keywords = meta.get("keywords", "")
            if "kpaperflux_immutable" not in current_keywords:
                meta["keywords"] = f"{current_keywords} kpaperflux_immutable".strip()
            
            doc_native.set_metadata(meta)

            # 5. Feature: Embed original if signed (Forensic traceability)
            if check_pdf_immutable(native_pdf):
                print(f"[HybridAssembler] Native PDF is signed. Embedding original: {native_pdf}")
                with open(native_pdf, "rb") as f:
                    file_content = f.read()
                # Fallback for different PyMuPDF versions for embedding (API evolved v1.11 -> v1.24)
                embed_func = None
                if hasattr(doc_native, "embedded_file_add"):
                    # Current Recommended API
                    embed_func = doc_native.embedded_file_add
                elif hasattr(doc_native, "embfile_add"):
                    # Newer shorthand preferred in some 1.2x.x documentations
                    embed_func = doc_native.embfile_add
                elif hasattr(doc_native, "embeddedFileAdd"):
                    # Legacy CamelCase (Pre 1.16.x)
                    embed_func = doc_native.embeddedFileAdd
                    
                if embed_func:
                    embed_func(
                        "original_source.pdf",
                        file_content,
                        filename="original_source.pdf",
                        desc="Original signed document used to create this hybrid."
                    )
                else:
                    print("[HybridAssembler] Warning: This version of PyMuPDF does not support embedding files.")
            
            # 6. Final Save
            doc_native.save(output_path, garbage=4, deflate=True)
            doc_native.close()
            doc_scan.close()
            
            return True
        except Exception as e:
            import traceback
            print(f"[HybridAssembler] Error: {e}")
            traceback.print_exc()
            return False
