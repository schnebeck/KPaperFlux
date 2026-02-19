
import os
import cv2
import fitz
import numpy as np
from pathlib import Path
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
        return self.tr("Hybrid Assembler")

    def get_description(self) -> str:
        return self.tr("Assembles hybrid PDFs from native and scanned versions.")

    def get_tool_actions(self, parent=None):
        from PyQt6.QtGui import QAction
        action = QAction(self.tr("Assemble Hybrid PDFs..."), parent)
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
        """
        try:
            doc_native = fitz.open(native_pdf)
            doc_scan = fitz.open(scan_pdf)
            
            # Log a warning if scan has fewer pages (potential missing signatures)
            if doc_scan.page_count < doc_native.page_count:
                print(f"[HybridAssembler] Warning: Scan has only {doc_scan.page_count} pages, but native has {doc_native.page_count}. Remaining native pages will have no signature overlay.")
            elif doc_scan.page_count > doc_native.page_count:
                print(f"[HybridAssembler] Note: Scan has {doc_scan.page_count} pages, native has {doc_native.page_count}. Ignoring extra scan pages.")

            engine = HybridEngine()

            # Process all pages of the native document to ensure it remains complete
            for i in range(doc_native.page_count):
                # Only overlay if we actually have a corresponding scanned page
                if i < doc_scan.page_count:
                    # 1. Render pages for analysis
                    img_native = engine.pdf_page_to_numpy(doc_native, i, dpi=300)
                    img_scan_raw = engine.pdf_page_to_numpy(doc_scan, i, dpi=300)
                    
                    # 2. Align and Extract signatures/stamps
                    img_scan_aligned, _ = engine.align_and_compare(img_native, img_scan_raw)
                    overlay_cv, pixel_count = engine.extract_high_fidelity_overlay(img_native, img_scan_aligned)

                    if overlay_cv is not None and pixel_count > 100:
                        # 3. Create transparent PNG
                        success, buffer = cv2.imencode(".png", overlay_cv, [cv2.IMWRITE_PNG_COMPRESSION, 9])
                        if success:
                            img_bytes = buffer.tobytes()
                            page_native = doc_native[i]
                            page_native.insert_image(page_native.rect, stream=img_bytes)

            # 4. Metadata handling
            standard_keys = ["title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate"]
            meta = {k: v for k, v in doc_native.metadata.items() if k in standard_keys}
            current_keywords = meta.get("keywords", "")
            if "kpaperflux_immutable" not in current_keywords:
                meta["keywords"] = f"{current_keywords} kpaperflux_immutable".strip()
            doc_native.set_metadata(meta)

            # 5. Feature: Embed original source
            with open(native_pdf, "rb") as f:
                file_content = f.read()
            
            embed_func = None
            for func_name in ["embedded_file_add", "embfile_add", "embeddedFileAdd"]:
                if hasattr(doc_native, func_name):
                    embed_func = getattr(doc_native, func_name)
                    break
                    
            if embed_func:
                embed_func("original_source.pdf", file_content, filename="original_source.pdf")
            
            # 6. Final Save
            doc_native.save(output_path, garbage=4, deflate=True)
            doc_native.close()
            doc_scan.close()
            
            return True
        except ValueError as ve:
            # Re-raise to be caught as string in the UI worker
            raise ve
        except Exception as e:
            print(f"[HybridAssembler] Error: {e}")
            raise e
