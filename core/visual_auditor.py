
import fitz  # PyMuPDF
import base64
import json
from typing import List, Dict, Any, Optional
import os

# ==============================================================================
# 1. KONFIGURATION
# ==============================================================================

AUDIT_MODE_FULL = "FULL_AUDIT"
AUDIT_MODE_STAMP = "STAMP_ONLY"
AUDIT_MODE_NONE = "NONE"

AUDIT_LEVEL_MAP = {
    AUDIT_MODE_FULL: 2,
    AUDIT_MODE_STAMP: 1,
    AUDIT_MODE_NONE: 0
}

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

SIGNATURE_KEYWORDS_HIGH = ["unterschrift", "signature", "gez.", "signed by", "auftragnehmer", "contractor", "arbeitgeber", "employer", "unterzeichner"]
SIGNATURE_KEYWORDS_LOW = ["ort", "datum", "date"]
SIGNATURE_THRESHOLD = 10

# ==============================================================================
# 2. PROMPTS (STAMP vs. FULL)
# ==============================================================================

# Prompt A: Forensic Stamp Auditor (User Defined)
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
    "suggested_types": ["String"], // Only if is_type_match is False
    "reasoning": "String"
  },

  "arbiter_decision": {
    "raw_ocr_quality_score": Integer (0-100),
    "ai_vision_quality_score": Integer (0-100),
    "primary_source_recommendation": "RAW_OCR | AI_VISION",
    "reasoning": "String"
  }
}
"""

# Prompt B: Forensic Full Audit (Stamps + Signatures)
PROMPT_STAGE_1_5_FULL = """
You are a Forensic Document Auditor & Signature Verifier.
Your goal is to audit the document structure, extract overlays (forms/stamps), and validate signatures.

### INPUTS
1. **IMAGES:** - `FIRST_PAGE`: Visual scan of the start of the document.
   - `SIGNATURE_PAGE`: Visual scan of the page likely containing signatures.
2. **RAW OCR:** Text extracted by standard OCR from the FIRST PAGE.
   >>> {raw_ocr_page1} <<<
3. **EXPECTED TYPES:** The system previously identified this as: {expected_types}

### MISSION 0: IDENTITY & TYPE INTEGRITY
- Quickly verify the document type based on visual clues (Logos, Titles).
- If the visual evidence contradicts the EXPECTED TYPES, flag it.

### MISSION 1: THE DOCUMENT LAYER (X-Ray Mode on FIRST_PAGE)
- Focus on the **FIRST_PAGE**.
- Visually "remove" any ink stamps or handwritten notes.
- Transcribe the **clean underlying printed text**.
- **Repair:** If a stamp covers text, infer the covered characters from context.
- **Constraint:** Do NOT include the stamp text in this transcription!

### MISSION 2: THE STAMP LAYER (Form Extraction Mode on FIRST_PAGE)
- Focus on the **FIRST_PAGE**.
- Focus ONLY on the stamps/handwriting ignored in Mission 1.
- **GEOMETRIC MAPPING:** Treat stamps as forms (Labels <-> Values).
- **NORMALIZATION:** - Dates to ISO YYYY-MM-DD.
  - Numbers to Float.
  - Empty fields to null.

### MISSION 3: THE SIGNATURE AUDIT (on SIGNATURE_PAGE)
- Focus on the **SIGNATURE_PAGE**.
- Check for **handwritten** or **digital** signatures in signature blocks.
- **Context:** A blank line is NOT a signature. Look for ink marks.

### MISSION 4: THE ARBITER (Quality Control on FIRST_PAGE)
- Compare "Document Layer" (Mission 1) with "RAW OCR".

### OUTPUT SCHEMA (JSON ONLY)
{
  "layer_document": {
    "clean_text": "String (Repaired text)",
    "was_repair_needed": Boolean
  },
  "layer_stamps": [
    {
      "raw_content": "String",
      "type": "RECEIVED | PAID | COMPANY | INTERNAL_FORM | HANDWRITTEN_NOTE",
      "location": "String",
      "form_fields": [
        {
          "label": "String",
          "raw_value": "String",
          "normalized_value": "String | Number | null",
          "value_type": "DATE | TIME | NUMBER | TEXT | SIGNATURE | EMPTY"
        }
      ]
    }
  ],
  "integrity": {
    "is_type_match": Boolean,
    "suggested_types": ["String"],
    "reasoning": "String"
  },
  "signatures": {
    "has_signature": Boolean,
    "count": Integer,
    "type": "HANDWRITTEN | DIGITAL | NONE",
    "details": "String"
  },
  "arbiter_decision": {
    "raw_ocr_quality_score": Integer,
    "ai_vision_quality_score": Integer,
    "primary_source_recommendation": "RAW_OCR | AI_VISION",
    "reasoning": "String"
  }
}
"""

class VisualAuditor:
    def __init__(self, ai_analyzer):
        """
        :param ai_analyzer: Instance of AIAnalyzer to perform vision chat.
        """
        self.ai = ai_analyzer

    def get_audit_mode_for_entities(self, detected_entities: List[Dict]) -> str:
        """Aggregates requirements from all detected DocTypes (Maximum wins)."""
        max_level = 0
        final_mode = AUDIT_MODE_NONE
        
        for entity in detected_entities:
            dtype = entity.get('doc_type', 'OTHER')
            # Normalize enum string if needed (e.g. DocType.INVOICE -> INVOICE)
            if "." in dtype: dtype = dtype.split(".")[-1]
            
            req_mode = DOCTYPE_AUDIT_CONFIG.get(dtype, AUDIT_MODE_NONE)
            level = AUDIT_LEVEL_MAP.get(req_mode, 0)
            
            if level > max_level:
                max_level = level
                final_mode = req_mode
        return final_mode

    def generate_audit_images_and_text(self, pdf_path: str, mode: str, text_content: Optional[str] = None, target_pages: List[int] = None) -> Dict[str, Any]:
        """
        Generates Base64 images based on mode and text search.
        Restricted to target_pages (1-based) if provided.
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
        
        # Determine 0-based indices to scan
        if target_pages:
            # Filter out out-of-bounds
            scan_indices = [p-1 for p in target_pages if 1 <= p <= total_pages]
        else:
            scan_indices = list(range(total_pages))
            
        if not scan_indices:
             doc.close()
             return {"images": [], "page1_text": ""}
        
        images_payload = []
        page1_text = ""
        
        # Helper: Get text for a page (DB or Fitz)
        # Note: text_content usually matches the VIRTUAL document (already split?)
        # If text_content is passed, it is the content of the RANGE.
        # So index 0 in text_content corresponds to scan_indices[0].
        db_pages = text_content.split('\f') if text_content else []
        
        def get_page_text(phys_idx):
            # Map physical index to relative index in db_pages?
            if phys_idx in scan_indices:
                rel_idx = scan_indices.index(phys_idx)
                if rel_idx < len(db_pages):
                    return db_pages[rel_idx]
            try:
                return doc.load_page(phys_idx).get_text()
            except:
                return ""

        # --- 1. ALWAYS FIRST PAGE (of the range) ---
        first_page_idx = scan_indices[0]
        indices_with_labels = {first_page_idx: "FIRST_PAGE"}
        
        # Extract Text from First Page (for Prompt)
        page1_text = get_page_text(first_page_idx)
        if not page1_text: page1_text = "(OCR Extract Failed)"
        
        # --- 2. LOGIC FOR SIGNATURES (FULL_AUDIT) ---
        if mode == AUDIT_MODE_FULL:
            signature_page_index = -1
            best_score = 0
            
            # Smart Search within range
            for i in scan_indices:
                try:
                    text = get_page_text(i).lower()
                    score = 0
                    for kw in SIGNATURE_KEYWORDS_HIGH:
                        if kw in text: score += 10
                    for kw in SIGNATURE_KEYWORDS_LOW:
                        if kw in text: score += 1
                    
                    if score >= SIGNATURE_THRESHOLD:
                        # Found a candidate.
                        # If multiple candidates, usually the LAST one is the real signature page.
                        if score >= best_score:
                             best_score = score
                             signature_page_index = i
                except:
                    pass
            
            # Decision:
            if signature_page_index != -1:
                indices_with_labels[signature_page_index] = "SIGNATURE_PAGE"
                print(f"[Smart Audit] Signature candidate found on physical page {signature_page_index + 1} (Score: {best_score})")
            else:
                last_idx = scan_indices[-1]
                indices_with_labels[last_idx] = "SIGNATURE_PAGE"
                print("[Smart Audit] No keywords. Using last page of range as fallback.")

            # Special Case: Single Page Doc or First=Last
            if first_page_idx in indices_with_labels and indices_with_labels[first_page_idx] == "SIGNATURE_PAGE":
                 indices_with_labels[first_page_idx] = "FIRST_PAGE_AND_SIGNATURE_PAGE"

        # --- 3. RENDERING ---
        for idx, label in indices_with_labels.items():
            try:
                page = doc.load_page(idx)
                # Matrix 4.16 = ~300 DPI for high-resolution visual analysis (Stamps/Signatures)
                pix = page.get_pixmap(matrix=fitz.Matrix(4.16, 4.16))
                
                from PIL import Image
                import io
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

    def run_stage_1_5(self, pdf_path: str, doc_uuid: str, stage_1_result: Dict, text_content: Optional[str] = None, target_pages: List[int] = None) -> Dict:
        """
        Executes audit and returns result dict.
        """
        print(f"--- Running Stage 1.5 (Visual Audit) for {doc_uuid} ---")
        
        # 1. Determine Mode
        entities = stage_1_result.get('detected_entities', [])
        audit_mode = self.get_audit_mode_for_entities(entities)
        print(f"Decided Audit Mode: {audit_mode}")
        
        if audit_mode == AUDIT_MODE_NONE:
            return {"meta_mode": AUDIT_MODE_NONE}
            
        # 2. Generate Images & Text
        data = self.generate_audit_images_and_text(str(pdf_path), audit_mode, text_content=text_content, target_pages=target_pages)
        audit_images_data = data["images"]
        
        # Prefer validation text from DB (text_content) if available, else fitz
        if text_content:
            pages = text_content.split('\f')
            raw_ocr_page1 = pages[0] if pages else text_content
        else:
             raw_ocr_page1 = data["page1_text"]
        
        if not audit_images_data:
            print("[VisualAuditor] No images generated. Skipping.")
            return {"meta_mode": "NONE"}
            
        # 3. Select & Format Prompt
        base_prompt = PROMPT_STAGE_1_5_FULL if audit_mode == AUDIT_MODE_FULL else PROMPT_STAGE_1_5_STAMP
        
        # Inject Contextual Data
        doc_types = [ent.get('doc_type', 'OTHER') for ent in entities]
        system_prompt = base_prompt.replace("{raw_ocr_page1}", raw_ocr_page1 if raw_ocr_page1 else "(No text found)")
        system_prompt = system_prompt.replace("{expected_types}", str(doc_types))
        
        # 4. Construct Content List for Gemini
        contents = [system_prompt]
        
        for item in audit_images_data:
            label = item['label']
            img = item['image']
            contents.append(f"\n[IMAGE CONTEXT: {label}]\n")
            contents.append(img)
            
        # 5. Call AI
        # print(f"\n=== [DEBUG] STAGE 1.5 AUDIT PROMPT ({audit_mode}) ===\n")
        # print(system_prompt) 
        
        # Upgrade: Use robust retry handler
        response = self.ai._generate_with_retry(contents)
        
        if response and response.text:
            txt = response.text
            if "```json" in txt:
                txt = txt.replace("```json", "").replace("```", "")
            
            try:
                res_json = json.loads(txt)
                res_json["meta_mode"] = audit_mode
                print("\n=== [STAGE 1.5 AUDIT RESULT] ===")
                print(json.dumps(res_json, indent=2))
                return res_json
            except json.JSONDecodeError:
                print(f"Stage 1.5 Invalid JSON: {txt[:200]}...")
            
        return {}
