from typing import Any, Dict, List, Optional
from PyQt6.QtGui import QAction
from core.plugins.base import KPaperFluxPlugin
from core.utils.hybrid_engine import HybridEngine
from core.utils.forensics import check_pdf_immutable
import fitz
import os
import cv2

class HybridAssemblerPlugin(KPaperFluxPlugin):
    """
    Plugin to create Hybrid PDFs.
    A Hybrid PDF contains:
    1. The Native (Born-Digital) text layer.
    2. The Scanned (Signed) image layer aligned to the text.
    3. Metadata marking it as immutable.
    """
    
    def __init__(self, api):
        super().__init__(api)
        self._matching_dialog = None

    def run(self, hook: str, data: Any = None) -> Any:
        return None

    def get_tool_actions(self, parent=None) -> List[Any]:
        action = QAction("Hybrid Matching-Dialog...", parent)
        action.triggered.connect(self.open_matching_dialog)
        return [action]

    def open_matching_dialog(self):
        from plugins.hybrid_assembler.matching_dialog import MatchingDialog
        
        if self._matching_dialog is not None:
            self._matching_dialog.activateWindow()
            self._matching_dialog.raise_()
            return
            
        self._matching_dialog = MatchingDialog(self.api.main_window, plugin=self)
        self._matching_dialog.finished_closing.connect(self._on_dialog_closed)
        self._matching_dialog.show()

    def _on_dialog_closed(self):
        self._matching_dialog = None

    def on_compare_clicked(self, doc_uuid: str):
        from gui.comparison_dialog import ComparisonDialog
        from PyQt6.QtWidgets import QFileDialog
        
        print(f"[HybridAssembler] Comparing {doc_uuid}")
        if not self.api.main_window or not self.api.logical_repo or not self.api.vault:
            return

        # 1. Get path for document in Vault
        v_doc = self.api.logical_repo.get_by_uuid(doc_uuid)
        if not v_doc or not v_doc.source_mapping:
            print("[HybridAssembler] Error: Document not found or has no source.")
            return
            
        phys_uuid = v_doc.source_mapping[0].file_uuid
        left_path = self.api.vault.get_file_path(phys_uuid)

        if not left_path or not os.path.exists(left_path):
            print(f"[HybridAssembler] Error: File not found in vault: {left_path}")
            return
        
        # 2. Ask for second file (the Scan)
        right_path, _ = QFileDialog.getOpenFileName(
            self.api.main_window, 
            self.api.main_window.tr("Select Scan to Compare"), 
            "", 
            self.api.main_window.tr("PDF Files (*.pdf);;All Files (*)")
        )
        
        if right_path:
            dlg = ComparisonDialog(self.api.main_window)
            dlg.load_comparison(left_path, right_path)
            dlg.exec()

    def create_hybrid(self, native_pdf: str, scan_pdf: str, output_path: str) -> bool:
        """
        Main logic for assembling the hybrid.
        For each page:
        - Render native and scan.
        - Align scan to native.
        - Place native text over aligned image.
        """
        try:
            doc_native = fitz.open(native_pdf)
            doc_scan = fitz.open(scan_pdf)
            doc_out = fitz.open()

            engine = HybridEngine()

            for i in range(min(doc_native.page_count, doc_scan.page_count)):
                # 1. Align
                img_native = engine.pdf_page_to_numpy(doc_native, i, dpi=150)
                img_scan = engine.pdf_page_to_numpy(doc_scan, i, dpi=150)
                
                img_aligned, similarity = engine.align_and_compare(img_native, img_scan)

                # 2. Create New Page
                page_native = doc_native[i]
                rect = page_native.rect
                new_page = doc_out.new_page(width=rect.width, height=rect.height)

                # 3. Add Aligned Image as Backdrop
                # Convert aligned CV2 image back to bytes for fitz
                success, buffer = cv2.imencode(".png", img_aligned)
                if success:
                    img_bytes = buffer.tobytes()
                    new_page.insert_image(rect, stream=img_bytes)

                # 4. Add Native Text Layer (Transparent)
                # This is tricky with fitz. Better to use pikepdf for precise layer merging,
                # but for now we can try to overlay the native content.
                new_page.show_pdf_page(rect, doc_native, i)

            # 5. Metadata handling
            standard_keys = ["title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate"]
            meta = {k: v for k, v in doc_native.metadata.items() if k in standard_keys}
            
            # Use 'keywords' to store our immutable flag since custom keys in set_metadata are not allowed in some fitz versions
            current_keywords = meta.get("keywords", "")
            if "kpaperflux_immutable" not in current_keywords:
                meta["keywords"] = f"{current_keywords} kpaperflux_immutable".strip()
            
            doc_out.set_metadata(meta)

            # Feature: Embed original if signed
            if check_pdf_immutable(native_pdf):
                print(f"[HybridAssembler] Native PDF is signed. Embedding original: {native_pdf}")
                with open(native_pdf, "rb") as f:
                    file_content = f.read()
                doc_out.embedded_file_add(
                    "original_source.pdf",
                    file_content,
                    filename="original_source.pdf",
                    desc="Original signed document used to create this hybrid."
                )
            
            doc_out.save(output_path, garbage=4, deflate=True)
            doc_out.close()
            doc_native.close()
            doc_scan.close()
            
            return True
        except Exception as e:
            print(f"[HybridAssembler] Error: {e}")
            return False

# Entry point for the PluginManager
def get_plugin_class():
    return HybridAssemblerPlugin
