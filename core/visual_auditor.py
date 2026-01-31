"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/visual_auditor.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Forensic document auditor that integrates AI-vision to identify
                and analyze stamps, handwriting, and signatures. Implements 
                multi-layered audit modes based on document type criticality.
------------------------------------------------------------------------------
"""

import base64
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import fitz  # PyMuPDF
from PIL import Image

# Audit Modes
AUDIT_MODE_FULL = "FULL_AUDIT"
AUDIT_MODE_STAMP = "STAMP_ONLY"
AUDIT_MODE_NONE = "NONE"

AUDIT_LEVEL_MAP = {
    AUDIT_MODE_FULL: 2,
    AUDIT_MODE_STAMP: 1,
    AUDIT_MODE_NONE: 0
}

# Configuration for document-type specific audit depth
DOCTYPE_AUDIT_CONFIG = {
    # --- LEVEL 2: FULL AUDIT ---
    "CONTRACT": AUDIT_MODE_FULL,
    "INSURANCE_POLICY": AUDIT_MODE_FULL,
    "LEGAL_CORRESPONDENCE": AUDIT_MODE_FULL,
    "OFFICIAL_LETTER": AUDIT_MODE_FULL,
    "SICK_NOTE": AUDIT_MODE_FULL,
    "TRAVEL_REQUEST": AUDIT_MODE_FULL,
    "APPLICATION": AUDIT_MODE_FULL,
    "DELIVERY_NOTE": AUDIT_MODE_FULL,
    "EXPENSE_REPORT": AUDIT_MODE_FULL,

    # --- LEVEL 1: STAMP ONLY ---
    "INVOICE": AUDIT_MODE_STAMP,
    "ORDER": AUDIT_MODE_STAMP,
    "ORDER_CONFIRMATION": AUDIT_MODE_STAMP,
    "CREDIT_NOTE": AUDIT_MODE_STAMP,
    "RECEIPT": AUDIT_MODE_STAMP,
    "DUNNING": AUDIT_MODE_STAMP,
    "TAX_ASSESSMENT": AUDIT_MODE_STAMP,
    "UTILITY_BILL": AUDIT_MODE_STAMP,

    # --- LEVEL 0: NONE ---
    "MANUAL": AUDIT_MODE_NONE,
    "DATASHEET": AUDIT_MODE_NONE,
    "TECHNICAL_DOC": AUDIT_MODE_NONE,
    "PAYSLIP": AUDIT_MODE_NONE,
    "BANK_STATEMENT": AUDIT_MODE_NONE,
    "CERTIFICATE": AUDIT_MODE_NONE,
    "VEHICLE_REGISTRATION": AUDIT_MODE_NONE,
    "NOTE": AUDIT_MODE_NONE,
    "OTHER": AUDIT_MODE_NONE
}

SIGNATURE_KEYWORDS_HIGH = [
    "unterschrift", "signature", "gez.", "signed by",
    "auftragnehmer", "contractor", "arbeitgeber", "employer", "unterzeichner"
]
SIGNATURE_KEYWORDS_LOW = ["ort", "datum", "date"]
SIGNATURE_THRESHOLD = 10

# Prompt A: Forensic Stamp Auditor
PROMPT_STAGE_1_5_STAMP = """
You are a Forensic Document Auditor.
Your goal is to separate the document into two distinct layers (Document Text vs. Stamp/Overlay) and analyze the stamp layer as a structured form.

### INPUTS
1. **IMAGE:** Visual scan of the **FIRST_PAGE**.
2. **RAW OCR:** Text extracted by standard OCR from the First Page.
   >>> {raw_ocr_page1} <<<
3. **EXPECTED TYPES:** The system previously identified this as: {expected_types}

### MISSION 0: IDENTITY & TYPE INTEGRITY
- Quickly verify the document type based on visual clues (Logos, Titles).
- If the visual evidence contradicts the EXPECTED TYPES, flag it.

### MISSION 1: THE DOCUMENT LAYER (X-Ray Mode)
- Visually "remove" any ink stamps, handwritten notes, or stains.
- Transcribe the **clean underlying printed text** of the document.
- **Repair:** If a stamp covers text (e.g. Invoice Number), infer the covered characters from context.
- **Constraint:** Do NOT include the stamp text in this transcription!

### MISSION 2: THE STAMP LAYER (Form Extraction Mode)
- Focus ONLY on the stamps, handwriting, and stickers ignored in Mission 1.
- **GEOMETRIC MAPPING (CRITICAL):** Treat each stamp as a structured form.
  1. Identify **Labels** (printed text on the stamp, e.g. "Kostenstelle", "Datum", "Sachlich richtig", "Eingang").
  2. Identify **Values** (handwritten or stamped content geometrically next to or below the label).
  3. Identify **Standalone Values** (content without a label, e.g. a date stamp floating freely).

- **NORMALIZATION RULES (Apply heuristic based on content):**
  - If Value looks like a **DATE**: Convert to ISO **YYYY-MM-DD**. (Context: Year '25' = 2025).
  - If Value looks like a **TIME**: Convert to 24h format **HH:MM**.
  - If Value looks like a **NUMBER** (Amount, Count, Percent): Convert to **Float** (e.g. 10.50).
  - If Value is **TEXT** (Codes, IDs, Names): Transcribe exactly.
  - If Value is **EMPTY** (Label present but no entry): Return `null` and type `EMPTY`.

### MISSION 3: THE ARBITER (Quality Control)
- Compare your "Document Layer" transcription with the provided "RAW OCR".
- Determine if the Raw OCR is corrupted by the stamps/overlays.
- Decide which source is safer for extracting numbers/dates.

### OUTPUT SCHEMA (JSON ONLY)
{
  "layer_document": {
    "clean_text": "String (Full page text, REPAIRED, without stamps)",
    "was_repair_needed": Boolean
  },

  "layer_stamps": [
    {
      "raw_content": "String (Full combined text of this specific stamp block)",
      "type": "RECEIVED | PAID | COMPANY | INTERNAL_FORM | HANDWRITTEN_NOTE",
      "location": "TOP_RIGHT | TOP_LEFT | BOTTOM | CENTER",
      "form_fields": [
        {
          "label": "String (The printed field name, e.g. 'Kostenstelle', or 'IMPLIED_DATE' if standalone)",
          "raw_value": "String (What is actually written, e.g. '9/12/25' or null)",
          "normalized_value": "String | Number | null (The formatted result)",
          "value_type": "DATE | TIME | NUMBER | TEXT | SIGNATURE | EMPTY"
        }
      ]
    }
  ],

  "integrity": {
    "is_type_match": Boolean,
    "suggested_types": ["String"]
  },

  "arbiter_decision": {
    "raw_ocr_quality_score": Integer (0-100),
    "ai_vision_quality_score": Integer (0-100),
    "primary_source_recommendation": "RAW_OCR | AI_VISION"
  }
}
"""

# Prompt B: Forensic Full Audit (Stamps + Signatures)
PROMPT_STAGE_1_5_FULL = """
You are a Forensic Document Auditor & Signature Verifier.
Your goal is to audit the document structure, extract overlays (forms/stamps), and validate signatures.

### MISSION 1: THE DOCUMENT LAYER (X-Ray Mode on FIRST_PAGE)
... (Same as Stamp Auditor)

### MISSION 2: THE STAMP LAYER (Form Extraction Mode on FIRST_PAGE)
... (Same as Stamp Auditor)

### MISSION 3: THE SIGNATURE AUDIT (on SIGNATURE_PAGE)
- Focus on the **SIGNATURE_PAGE**.
- Check for **handwritten** or **digital** signatures in signature blocks.
- **Context:** A blank line is NOT a signature. Look for ink marks.

### MISSION 4: THE ARBITER (Quality Control on FIRST_PAGE)
... (Same as Stamp Auditor)

### OUTPUT SCHEMA (JSON ONLY)
... (Similar to Stamp Auditor + signatures block)
{
  ...
  "signatures": {
    "has_signature": Boolean,
    "count": Integer,
    "type": "HANDWRITTEN | DIGITAL | NONE",
    "details": "String"
  },
  ...
}
"""


class VisualAuditor:
    """
    Forensic document auditor implementation.
    Orchestrates AI vision tasks to analyze physical overlays like stamps and signatures.
    """

    def __init__(self, ai_analyzer: Any) -> None:
        """
        Initializes the VisualAuditor.

        Args:
            ai_analyzer: Instance of AIAnalyzer to perform vision requests.
        """
        self.ai: Any = ai_analyzer

    def get_audit_mode_for_entities(self, detected_entities: List[Dict[str, Any]]) -> str:
        """
        Determines the required audit depth based on document types.

        Args:
            detected_entities: List of entity dictionaries with 'doc_type'.

        Returns:
            The highest required audit mode string.
        """
        max_level = 0
        final_mode = AUDIT_MODE_NONE

        for entity in detected_entities:
            dtype = str(entity.get('doc_type', 'OTHER')).upper()
            if "." in dtype:
                dtype = dtype.split(".")[-1]

            req_mode = DOCTYPE_AUDIT_CONFIG.get(dtype, AUDIT_MODE_NONE)
            level = AUDIT_LEVEL_MAP.get(req_mode, 0)

            if level > max_level:
                max_level = level
                final_mode = req_mode
        return final_mode

    def generate_audit_images_and_text(self, pdf_path: str, mode: str, text_content: Optional[str] = None, target_pages: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Renders relevant pages for forensic analysis and retrieves OCR text.

        Args:
            pdf_path: Path to the physical PDF.
            mode: The audit mode (STAMP or FULL).
            text_content: Optional pre-existing OCR text.
            target_pages: Optional list of 1-based page numbers to restrict scanning.

        Returns:
            A dictionary containing 'images' (List of labeled PIL images) and 'page1_text'.
        """
        if not os.path.exists(pdf_path):
            print(f"[VisualAuditor] File not found: {pdf_path}")
            return {"images": [], "page1_text": ""}

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"[VisualAuditor] Failed to open PDF with fitz: {e}")
            return {"images": [], "page1_text": ""}

        total_pages = doc.page_count

        # Determine 0-based physical page indices for scan
        if target_pages:
            scan_indices = [p - 1 for p in target_pages if 1 <= p <= total_pages]
        else:
            scan_indices = list(range(total_pages))

        if not scan_indices:
            doc.close()
            return {"images": [], "page1_text": ""}

        images_payload: List[Dict[str, Any]] = []
        page1_text = ""
        db_pages = text_content.split('\f') if text_content else []

        def get_page_text(phys_idx: int) -> str:
            """Retrieves OCR text for a physical page index."""
            if phys_idx in scan_indices:
                rel_idx = scan_indices.index(phys_idx)
                if rel_idx < len(db_pages):
                    return db_pages[rel_idx]
            try:
                return doc.load_page(phys_idx).get_text()
            except Exception:
                return ""

        # 1. First Page Logic
        first_page_idx = scan_indices[0]
        indices_with_labels = {first_page_idx: "FIRST_PAGE"}
        page1_text = get_page_text(first_page_idx) or "(OCR Extract Failed)"

        # 2. Signature Page Hunt (only in FULL mode)
        if mode == AUDIT_MODE_FULL:
            signature_page_index = -1
            best_score = 0

            for i in scan_indices:
                text = get_page_text(i).lower()
                score = 0
                for kw in SIGNATURE_KEYWORDS_HIGH:
                    if kw in text:
                        score += 10
                for kw in SIGNATURE_KEYWORDS_LOW:
                    if kw in text:
                        score += 1

                if score >= SIGNATURE_THRESHOLD and score >= best_score:
                    best_score = score
                    signature_page_index = i

            if signature_page_index != -1:
                if signature_page_index == first_page_idx:
                    indices_with_labels[first_page_idx] = "FIRST_PAGE_AND_SIGNATURE_PAGE"
                else:
                    indices_with_labels[signature_page_index] = "SIGNATURE_PAGE"
            else:
                # Fallback to last page of range
                last_idx = scan_indices[-1]
                if last_idx == first_page_idx:
                    indices_with_labels[first_page_idx] = "FIRST_PAGE_AND_SIGNATURE_PAGE"
                else:
                    indices_with_labels[last_idx] = "SIGNATURE_PAGE"

        # 3. Rendering relevant pages at high DPI
        for idx, label in indices_with_labels.items():
            try:
                page = doc.load_page(idx)
                # High resolution (approx 300 DPI) for visual analysis
                pix = page.get_pixmap(matrix=fitz.Matrix(4.16, 4.16))
                img_data = pix.tobytes("png")
                pil_img = Image.open(io.BytesIO(img_data))

                images_payload.append({
                    "image": pil_img,
                    "label": label
                })
            except Exception as e:
                print(f"[VisualAuditor] Render error page {idx}: {e}")

        doc.close()
        return {
            "images": images_payload,
            "page1_text": page1_text
        }

    def run_stage_1_5(self, pdf_path: Union[str, Path], doc_uuid: str, stage_1_result: Dict[str, Any], text_content: Optional[str] = None, target_pages: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Executes the Stage 1.5 Forensic Audit via AI vision.

        Args:
            pdf_path: Path to the physical PDF source.
            doc_uuid: Virtual document UUID.
            stage_1_result: The JSON result from Stage 1 analysis.
            text_content: Optional full OCR text.
            target_pages: Optional 1-based page list for logical document.

        Returns:
            A dictionary containing the audit findings.
        """
        entities = stage_1_result.get('detected_entities', [])
        audit_mode = self.get_audit_mode_for_entities(entities)

        if audit_mode == AUDIT_MODE_NONE:
            return {"meta_mode": AUDIT_MODE_NONE}

        # Render relevant pages
        data = self.generate_audit_images_and_text(str(pdf_path), audit_mode, text_content=text_content, target_pages=target_pages)
        audit_images_data = data["images"]
        raw_ocr_page1 = data["page1_text"]

        if not audit_images_data:
            return {"meta_mode": AUDIT_MODE_NONE}

        # Prepare Prompt
        base_prompt = PROMPT_STAGE_1_5_FULL if audit_mode == AUDIT_MODE_FULL else PROMPT_STAGE_1_5_STAMP
        doc_types = [ent.get('doc_type', 'OTHER') for ent in entities]

        system_prompt = base_prompt.format(
            raw_ocr_page1=raw_ocr_page1,
            expected_types=str(doc_types)
        )

        # Gemini Multimodal Content
        contents: List[Union[str, Image.Image]] = []
        for item in audit_images_data:
            contents.append(f"\n[IMAGE CONTEXT: {item['label']}]\n")
            contents.append(item['image'])

        # AI Execution
        res_json = self.ai._generate_json(
            system_prompt,
            stage_label=f"STAGE 1.5 AUDIT ({audit_mode})",
            images=contents
        )

        if res_json:
            res_json["meta_mode"] = audit_mode
            return res_json

        return {"meta_mode": AUDIT_MODE_NONE}
