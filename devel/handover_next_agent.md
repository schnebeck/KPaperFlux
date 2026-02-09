# **Handover: Current Task State**

## **Status Overview (as of 2026-02-09)**
The **Hybrid PDF Workflow** is fully implemented, and the system has transitioned into the **Reporting & Workflow Phase**. The foundation has been refactored to a JSON-first metadata structure, and a flexible UI policy system for PDF viewing is now active. The test suite remains stable (219/219 passed).

---

## **Recent Achievements (Finalized & Verified)**
1.  **Flexible Toolbar Policy:**
    *   `PdfViewerWidget` now uses a named policy system ('standard', 'comparison', 'audit').
    *   Symmetrical layouts are maintained via `setRetainSizeWhenHidden(True)` placeholders.
    *   Rotation and Delete buttons adapt visibility and activity based on the document context (Immutable, Hybrid, or Audit side).
2.  **Audit & Verification Ready:**
    *   `AuditWindow` is optimized for side-by-side verification: Original (left, rotatable) vs. Semantic Render (right, locked).
3.  **UI & Consistency:**
    *   Page counter restored to "x / y" format with editable current page.
    *   Styling of navigation/zoom controls enhanced (Bold/Bold Symbols).
    *   Visual-only rotation for direct files implemented in `PdfCanvas`.
4.  **Forensic Traceability:**
    *   Signed PDFs automatically embed original sources as attachments.
    *   Immutability protection prevents destructive GUI actions on PAdES/Protected files.

---

## **Strategic Roadmap (Next Steps)**

### 1. The Reporting Engine (`core/reporting.py`)
Implementation of the interpretative layer for extracted data:
*   **Finance Hub:** Aggregate amounts, tax breakdowns, and monthly summaries.
*   **Excel-Optimized Export:** CSV exports using `utf-8-sig` (BOM) for seamless spreadsheet integration.
*   **Strategy Pattern:** Decouple data sources from output formats (JSON, CSV, PDF).

### 2. Actionability & Quick Wins
*   **GiroCode Integration:** Generate EPC-QR codes directly from extracted IBAN/Amount data.
*   **Dashboarding:** Initial bar charts/KPIs in the main window to visualize burn rates and categories.

### 3. Generic Workflow Engine (State Machine)
Transition from hard-coded states to programmable Playbooks:
*   **State Machine:** Define YAML/JSON playbooks for document lifecycles (e.g., `NEW` -> `VERIFIED` -> `PAID`).
*   **Adaptive Editor:** The Metadata Editor should adapt its fields/requirements based on the current state of the playbook.

### 4. Integrity Status Bar & ZUGFeRD 0.5
*   Add a slim status overlay to the PDF viewer for:
    *   🛡️ **Signature Status** (PAdES verification).
    *   ⚙️ **Structured Data** (ZUGFeRD XML found).
    *   📎 **Attachments** (Original source access).
*   **Stage 0.5 Pipeline:** Inject XML data directly into `SemanticExtraction` before AI processing to save tokens and ensure 100% accuracy.

---

## **Environment Details**
*   **Core:** Python 3.12+, PyQt6.
*   **Key Libraries:** PyMuPDF (fitz), OpenCV, NumPy.
*   **Strategic Docs:** See `@devel/strategic_evaluation.md` for the full reporting concept.

---
*End of Handover Documentation*
