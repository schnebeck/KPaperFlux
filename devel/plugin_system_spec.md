# **Specification: KPaperFlux Plugin System & Specialized PDF Support**

## **1. Vision**
KPaperFlux will be extended into a modular platform where specialized document processing (like Hybrid PDF assembly, DATEV export, or Custom OCR) can be implemented as independent plugins. These plugins have access to the core via a stable API (`ApiContext`) and can provide their own GUI components.

---

## **2. Plugin Architecture (Implemented)**

### **2.1 Directory Structure**
Plugins reside in a dedicated `plugins/` folder. The loader discovery is managed by `core.plugins.manager.PluginManager`.
```text
plugins/
├── hybrid_assembler/
│   ├── manifest.json       # Metadata: name, version, author, entry_point
│   ├── plugin.py           # Main plugin class inheriting from KPaperFluxPlugin
│   └── matching_dialog.py  # Plugin-specific UI components
└── ...
```

### **2.2 The `KPaperFluxPlugin` Base Class**
Defined in `core.plugins.base.py`. Every plugin must inherit from this class.
```python
class KPaperFluxPlugin:
    def __init__(self, api_context):
        self.api = api_context  # Stable Gateway to KPaperFlux Core

    def get_name(self) -> str:
        return "Hybrid Assembler"

    def get_tool_actions(self, parent=None):
        """Returns a list of QAction objects for the Tools menu."""
        return []
```

---

## **3. The Internal API (`ApiContext`)**
The `ApiContext` (in `core.plugins.base.py`) acts as a bridge, currently providing:
*   **Main Window Access:** `api.main_window` for triggering imports and UI interactions.
*   **Future Extensions:** Planned access to `api.db`, `api.vault`, and `api.config`.

---

## **4. Specialist PDF Support: "Hybrid Workflow"**

### **4.1 Dual PDF Viewer & Match Analysis**
The `DualPdfViewerWidget` (in `gui.pdf_viewer.py`) provides the UI for side-by-side comparison.
*   **Synchronized Scrolling:** Percentage-based sync for mismatched page sizes.
*   **Zoom Mastering:** Left viewer acts as the scale master; right viewer follows with a persistent delta.
*   **Match Analysis:** Integrated `HybridEngine` for creating visual diff overlays (Cyan for Deletions, Red for Additions).

### **4.2 Hybrid Assembler Strategy (V3 - Overlay-Only)**
The assembler has moved from a full-scan background to a high-fidelity overlay strategy:
1.  **Base:** Original Native PDF (keeps vector text and searchability).
2.  **Extraction:** Scanned signatures/stamps are extracted as transparent PNGs at 300 DPI.
3.  **Assembly:** Transparent layers are inserted into the native PDF.
4.  **Forensics:** The original signed document is embedded as a PDF attachment within the hybrid file.

---

## **5. Protection & Immutability**

### **5.1 Immutable Flag**
Documents can be marked via the `kpaperflux_immutable` keyword in PDF metadata.
*   **Detection:** Handled by `core.utils.forensics.check_pdf_immutable`.
*   **Safety:** Checks for Digital Signatures (multi-version PyMuPDF support) and metadata flags.
*   **Workflow:** Immutable documents bypass the splitter and are sent directly to semantic analysis.

---

## **6. Implementation Status (Updated 2026-02-09)**

1.  **Done (Core):** `PluginManager`, `ApiContext`, and `KPaperFluxPlugin` base classes implemented.
2.  **Done (UI):** `DualPdfViewerWidget` with master-slave sync and visual diff support.
3.  **Done (Plugin):** `HybridAssemblerPlugin` fully functional, using the optimized overlay strategy.
4.  **Done (Maintenance):** Robust PyMuPDF version compatibility for forensic checks (v1.18 - v1.24+).
5.  **Planned:** Expanding the `ApiContext` to provide more granular DB and Rules Engine access to plugins.

---
*End of Specification Documentation*
