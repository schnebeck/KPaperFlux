"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/importer.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Pre-flight importer for converting various input formats (Images,
                ZIPs) into a standardized PDF format for further processing.
------------------------------------------------------------------------------
"""

import os
import zipfile
from typing import Set

import fitz  # PyMuPDF


class PreFlightImporter:
    """
    Handles the conversion of non-PDF source files into a standardized PDF format.
    """

    # Whitelist for allowed image formats
    ALLOWED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}

    @staticmethod
    def convert_to_pdf(input_path: str, output_path: str) -> bool:
        """
        Converts image files or ZIP archives into a standardized PDF.
        Uses PyMuPDF for maximum performance.

        Args:
            input_path: Path to source file (ZIP or Image).
            output_path: Path where the temporary PDF should be saved.

        Returns:
            True on success, False on error or empty data.
        """
        ext = os.path.splitext(input_path)[1].lower()
        final_doc = fitz.open()  # The new PDF Container
        processed_count = 0

        try:
            # --- CASE A: ZIP ARCHIVE (Batch Import) ---
            if ext == ".zip":
                try:
                    with zipfile.ZipFile(input_path, "r") as z:
                        # Sort for logical page order
                        file_list = sorted(z.namelist())

                        for filename in file_list:
                            # Ignore Mac system folders and non-images
                            if "__MACOSX" in filename:
                                continue

                            _, sub_ext = os.path.splitext(filename)
                            if sub_ext.lower() not in PreFlightImporter.ALLOWED_EXTENSIONS:
                                continue

                            # Read image data directly into RAM
                            img_bytes = z.read(filename)

                            # Magic: Bytes -> Image Doc -> PDF Stream -> Insert
                            with fitz.open(stream=img_bytes, filetype=sub_ext[1:]) as img_doc:
                                pdf_bytes = img_doc.convert_to_pdf()
                                with fitz.open("pdf", pdf_bytes) as pdf_page:
                                    final_doc.insert_pdf(pdf_page)
                                    processed_count += 1
                except zipfile.BadZipFile:
                    print(f"[Importer] Error: {input_path} is not a valid ZIP.")
                    return False

            # --- CASE B: SINGLE FILE (Image / Multi-Page TIFF) ---
            elif ext in PreFlightImporter.ALLOWED_EXTENSIONS:
                # fitz.open handles multi-page TIFs automatically!
                with fitz.open(input_path) as img_doc:
                    pdf_bytes = img_doc.convert_to_pdf()
                    with fitz.open("pdf", pdf_bytes) as pdf_page:
                        final_doc.insert_pdf(pdf_page)
                        processed_count = img_doc.page_count

            else:
                # Unknown format -> Ignore
                return False

            # --- CONCLUSION: Save ---
            if processed_count > 0:
                # garbage=4: Resources deduplication (smaller files)
                # deflate=True: Stream compression
                final_doc.save(output_path, garbage=4, deflate=True)
                final_doc.close()
                print(f"[Importer] Success: {processed_count} pages converted to {output_path}")
                return True

            final_doc.close()
            print("[Importer] Warning: No convertible images found.")
            return False

        except Exception as e:
            print(f"[Importer] Critical Error converting {input_path}: {e}")
            if final_doc:
                final_doc.close()
            return False
