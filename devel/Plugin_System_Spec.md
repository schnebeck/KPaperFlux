# **Specification: KPaperFlux Plugin System & Specialized PDF Support**

## **1. Vision**
KPaperFlux will be extended into a modular platform where specialized document processing (like Hybrid PDF assembly, DATEV export, or Custom OCR) can be implemented as independent plugins. These plugins will have access to the core data via a stable API and can provide their own GUI components.

---

## **2. Plugin Architecture**

### **2.1 Directory Structure**
Plugins reside in a dedicated `plugins/` folder in the application data directory.
```text
plugins/
├── hybrid_assembler/
│   ├── manifest.json       # Metadata: name, version, author, entry_point
│   ├── main.py            # Main plugin class inheriting from BasePlugin
│   └── resources/          # Icons, UI files, etc.
└── custom_exporter/
    └── ...
```

### **2.2 The `KPaperFluxPlugin` Base Class**
Every plugin must inherit from this base class to be recognized by the loader.
```python
class KPaperFluxPlugin:
    def __init__(self, api_context):
        self.api = api_context  # Stable Gateway to KPaperFlux Core

    def get_info(self) -> dict:
        """Returns metadata about the plugin."""
        return {
            "name": "My Plugin",
            "version": "1.0.0",
            "hooks": ["ON_TRANSFER_SCAN", "ON_CONTEXT_MENU"]
        }

    def get_settings_widget(self, parent=None) -> QWidget:
        """Optional: returns a widget for the main settings dialog."""
        return None

    def run(self, hook_name, data=None):
        """Entry point called by the event loop."""
        pass
```

---

## **3. The Internal API (`ApiContext`)**
The `ApiContext` acts as a sandbox and bridge. It provides plugins with:

*   **Config Access:** `api.config.get_transfer_path()`
*   **Database Search:** `api.db.query_documents(filters, limit=100)`
*   **Vault Interactions:** `api.vault.get_file(uuid) -> Path`
*   **Rules Engine:** `api.rules.get_active_rules() -> List[Rule]`
*   **UI Components:** Access to shared widgets (see Section 4).

---

## **4. Extended UI Components for Plugins**

### **4.1 Side-By-Side PDF Viewer**
A new `DualPdfViewerWidget` will be introduced to allow comparison of documents (e.g., Native Source vs. Scanned Overlay).
*   **Features:** Synchronized scrolling, zoom locking.
*   **Usage for Hybrid Assembler:** Left side shows the Digital Original, Right side shows the Scan. Matches can be verified visually.

### **4.2 Signature Verification (KDE/SPOKE Integration)**
The PDF Viewer will be enhanced to detect and verify digital signatures.
*   **Backend:** Use `pyHanko` or `fitz.get_sig_flags()`.
*   **UI:** A "Shield" icon in the status bar of the viewer. Clicking it opens a verification panel showing the certificate authority and integrity status.
*   **KDE Integration:** If running on Plasma, use `ki18n` and potentially call `okular` via D-Bus for high-fidelity signature inspection if needed.

---

## **5. Specialized PDF Support: "Protected Entities"**

### **5.1 Immutable Flag**
Documents can be marked as `is_immutable` (stored in `virtual_documents.protection_level`).
*   **Protection:** Disables Splitting, Merging, and physical Stamping.
*   **Auto-Detection:** The `PreFlightImporter` checks for:
    1.  Digital Signatures.
    2.  Custom metadata (e.g., `kpaperflux_immutable: true`).
    3.  PDF/A-3 (ZUGFeRD) status.

### **5.2 Hybrid Processing Workflow**
1.  **Plugin-Veredelung:** The Hybrid Assembler Script runs in the Transfer folder.
2.  **Creation:** It Aligns Scan-Ink over the Native PDF.
3.  **Embed:** It embeds the Original as an attachment and/or ZUGFeRD XML.
4.  **Import:** KPaperFlux imports the result, detects the `immutable` status, and treats it as a high-fidelity unit.

---

## **6. Implementation Roadmap**

1.  **Phase 1 (Infrastructure):** Implemend `PluginLoader` and `ApiContext`.
2.  **Phase 2 (UI Shared):** Refactor `PdfViewerWidget` into a reusable component and build `DualPdfViewerWidget`.
3.  **Phase 3 (Signature):** Integrate signature detection into the Viewer.
4.  **Phase 4 (Sample Plugin):** Port the Hybrid Assembler Script into the new Plugin API.
5.  **Phase 5 (Finalization):** Refine and complete the specifications and documentation once the implementation is stable and all edge cases are addressed.
