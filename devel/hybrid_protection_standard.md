# Hybrid Protection Standard: KPaperFlux Importer Logic

This document defines the mandatory handling of special PDF types (signed, ZUGFeRD, encrypted) during import and processing within KPaperFlux.

## 1. Core Philosophy
KPaperFlux prioritizes **Data Integrity** while ensuring **Visual Traceability** (Stamping). We distinguish between the "Visual Rendition" (what the user sees) and the "Ground Truth" (signatures, XML data).

---

## 2. Document Classes & Handling

### 2.1 Class A: Digitally Signed PDFs (Legal Originals)
*   **Criteria:** PDF contains at least one digital signature (PAdES).
*   **Constraint:** Modifications to the binary PDF would break the signature.
*   **Strategy: "The Envelope Strategy"**
    1.  **Work Copy:** Render high-resolution images of all pages and create a new, unsigned PDF.
    2.  **Stamping:** Integrate the KPaperFlux stamp directly into the pages of this Work Copy.
    3.  **Encapsulation:** Embed the **Original Signed PDF** as an attachment (`original_signed_source.pdf`) into the Work Copy.
    4.  **Preservation:** Extract and also embed any ZUGFeRD XMLs from the original.
    5.  **Metadata:** Set `is_immutable = True` in the database to prevent further atomic splitting.

### 2.2 Class B: ZUGFeRD / Factur-X PDFs (Digital Invoices)
*   **Criteria:** PDF contains embedded XML data (CII/CrossIndustryInvoice) but is NOT signed.
*   **Constraint:** The PDF rendition is secondary; the XML is the primary proof.
*   **Strategy: "Extraction/Re-Embedding Strategy"**
    1.  **Extract:** Programmatically extract the `factur-x.xml` or `zugferd-invoice.xml`.
    2.  **Modify:** Apply the KPaperFlux stamp into the visual PDF layer.
    3.  **Restore:** Re-embed the identical XML into the modified PDF container.
    4.  **Metadata:** Ensure PDF/A-3 compliance tags are preserved/restored if possible.

### 2.3 Class C: Standard Scans (Physical Originals)
*   **Criteria:** Image-based PDFs without signatures or embedded XML.
*   **Strategy: "Native Integration"**
    1.  Apply stamps directly to the PDF data.
    2.  Standard OCR and AI analysis flow.

### 2.4 Class AB: Signed ZUGFeRD (Full Hybrid)
*   **Criteria:** PDF is digitally signed AND contains ZUGFeRD XML.
*   **Constraint:** Highest protection level. Signature must not break, XML must stay pinned.
*   **Strategy: "Unified Envelope"**
    1.  **Work Copy:** Render visual pages for work/stamping.
    2.  **Stamping:** Integrate KPaperFlux stamps into the Work Copy pages.
    3.  **Encapsulation:**
        *   Embed the **original signed PDF** (which already contains its XML).
        *   Additionally embed the extracted **XML separately** (for easy access by other tools).
    4.  **Metadata:** Set `is_immutable = True`.

---

## 3. UI/UX Requirements (The Splitter)

*   **Awareness:** The `SplitterDialog` must detect Class A and Class B before display.
*   **Visual Feedback:**
    *   Class A files are marked with 🛡️ (Protected Sign).
    *   Class B files are marked with ⚙️ (Machine Readable).
*   **Interlock:**
    *   Splitting, Merging, or Deleting pages of Class A/B documents is **disabled**.
    *   The user is notified: *"This document is a digital original and cannot be physically altered inside the splitter."*

---

## 4. Forensic Integration (Stage 1.5)

If a document arrives as a Class C scan but contains visual clues of a Class A/B origin (e.g., printed ZUGFeRD markers):
1.  **Prompt:** The AI should note the "Media Break".
2.  **Recommendation:** Suggest the user find and import the digital original for higher fidelity.

---
*Status: Implemented (UI Interlocks & Forensic Handlers Active)*
