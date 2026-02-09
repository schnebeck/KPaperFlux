# **Project Definition: KPaperFlux**

**Version:** 2.0.0
**Target Platform:** Linux (KDE Plasma)
**Core Technology:** Python 3.12, PyQt6 (Qt6), SQLite, Google Gemini AI (Vertex AI/Flash)

## **1. Project Vision & Architecture**

**KPaperFlux** is a native desktop application for intelligent document management (DMS) on KDE Plasma. It bridges the gap between traditional file-based archiving and modern AI-driven semantic analysis.

### **1.1 Architectural Decisions**

*   **Type:** Native "Thick Client" Desktop Application.
*   **Rationale:** Low-latency hardware access (Scanner/ADF), high-performance local image processing (OCR, despeckling, deskewing), and deep desktop integration.
*   **Storage Concept:** "Managed Immutable Vault". Documents are stored as physical files in an internal structure, while users interact with logical "Virtual Documents" via the GUI.
*   **Data Integrity:** Priority #1. Physical files are never modified after ingestion (WORM - Write Once Read Many).

## **2. Technology Stack**

| Component | Technology / Library | Purpose |
| :--- | :--- | :--- |
| **Language** | Python 3.12+ | Main logic and orchestration |
| **GUI** | PyQt6 | User interface, native KDE/Plasma look & feel |
| **Database** | SQLite + FTS5 | Metadata storage, JSON-based semantic data, full-text search |
| **Data Models** | Pydantic v2 | Schema validation, serialization, and type safety |
| **Scanner Interface** | python-sane | Acquisition from SANE-compatible scanners |
| **OCR & PDF** | PyMuPDF (fitz), pikepdf | PDF manipulation, extraction, and rendering |
| **Intelligence** | Google Gemini API | Semantic classification, entity extraction, and cross-source repair |

## **3. Functional Requirements**

### **3.1 The Processing Pipeline (The "Flux")**

Documents follow a strict multi-stage lifecycle:

1.  **Stage 0: Ingestion & Splitting:** Files are imported or scanned. Multi-document PDF stacks are logically split into individual entities based on AI instructions or manual user input.
2.  **Stage 1: Adaptive classification:** Using "Pre-Flight" checks (scanning headers/footers), the AI selects the optimal analysis strategy (SANDWICH, HEADER_SCAN, or FULL_READ) to minimize token consumption while maximizing accuracy.
3.  **Stage 1.5: Visual Audit:** Forensic analysis of the first page to detect stamps, signatures, and handwriting. Features an "Arbiter" that compares AI Vision results with raw OCR to decide on the most reliable data source.
4.  **Stage 2: Semantic Extraction:** Deep dive into specific document bodies (Finance, Legal, HR, etc.). Performs cross-page text repair and extracts high-fidelity metadata into a polymorphic JSON structure.

### **3.2 The Vault**

*   **Physical Layer:** Files are stored using UUIDs to prevent path collisions and sanitize filenames.
*   **Logical Layer (Virtual Documents):** A single virtual document can span multiple physical files or specific page ranges within a file.
*   **Deduplication:** Uses perceptual hashing (pHash) for visual duplicates and fuzzy OCR matching for content duplicates.

### **3.3 GUI & Interaction**

*   **Dynamic Search:** Combination of full-text search and faceted filtering using the JSON-based `semantic_data`.
*   **Metadata Editor:** Interactive editing of AI results with auto-completion based on normalized "Canonized" entities (Sellers, IBANs, etc.).
*   **Export:** Smart filename generation (`YYYY-MM-DD__Sender__Type.pdf`) and optional PDF/A flattening with interactive stamp overlays.

## **4. Data Model (V2 Schema)**

### **Physical Files**
Stores the immutable source material with OCR results.
*   `uuid` (PK): Unique file ID.
*   `file_path`: Internal storage path.
*   `raw_ocr_data`: JSON map of `page_num -> text`.
*   `page_count_phys`: Total physical pages.

### **Virtual Documents**
The user-facing logical document.
*   `uuid` (PK): Document ID.
*   `source_mapping`: JSON list of `{file_uuid, pages, rotation}`.
*   `status`: NEW, PROCESSING_S1, PROCESSING_S2, PROCESSED, etc.
*   `type_tags`: JSON list (e.g., `["INVOICE", "INBOUND"]`).
*   `semantic_data`: Dynamic JSON block containing the "Canonized" extraction.
*   `cached_full_text`: Consolidated text for FTS indexing.

## **5. Localization (l10n) & Rendering**

KPaperFlux uses a centralized localization architecture to manage internationalization (i18n) and visual rendering consistency.

### **5.1 Centralized l10n Structure**
All language-specific assets are consolidated in `resources/l10n/`:

*   **GUI Strings:** Qt Translation files (`gui_strings.ts` / `.qm`) for translating the desktop interface.
*   **Unit Codes:** ISO/UN standard codes (e.g., `C62` for "Stück") are mapped in `units.json`.
*   **Render Templates:** JSON-based templates for converting raw semantic extraction into human-readable HTML/Markdown or professional PDFs.

### **5.2 Directory Schema**
```text
resources/l10n/
├── de/
│   ├── gui_strings.ts|.qm  # UI Translations
│   ├── units.json          # ISO Unit Mappings
│   └── templates/          # Localized Render Templates
├── en/
│   ├── ...
└── common/
    └── templates/          # Global standard fallbacks
```

### **5.3 Logic Fallbacks**
1.  **Rendering:** Primary lookup in the current locale folder (`l10n/<lang>/templates`). Fallback to `l10n/common/templates`.
2.  **Units:** Primary lookup in the current locale. Fallback to English (`l10n/en/units.json`).
3.  **Formatting:** The `SemanticRenderer` provides l10n-aware formatters for currencies (e.g., `1.234,56 €`), dates (`DD.MM.YYYY`), and unit codes.
