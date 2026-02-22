# **Handover: Current Task State**

> [!IMPORTANT]
> **Agent Usage Instruction:** This file is the primary synchronization point between sessions.
> 1. **Read** this file at the start of every session.
> 2. **Update** this file regularly (at least after every significant milestone) to prevent information loss due to session timeouts or crashes.
> 3. **Document** achievements, current blockers, and the immediate next steps.

## **Status Overview (as of 2026-02-21)**
The application has reached a high level of linguistic and structural maturity. Our localization system is now strictly tool-driven, preventing manual syntax errors. We have completed a major refinement of the German UI terminology, shifting from technical/verbose labels to professional, concise German. The UI has been made more resilient to varying label lengths (multi-line support in Dashboard).

---

### **Achievements (Phase 116-200+)**
1. **Dynamic UI Refactoring (L10n Readiness):**
    *   **Principle:** Abolished fixed widths (`setFixedWidth`) in favor of dynamic sizing.
    *   **Dashboard Resilience:** Refactored `StatCard` (Cockpit) to support **Multi-Line Titles** (`setWordWrap(True)`) and top-aligned iconography.
2. **Advanced L10n Tooling & Governance:**
    *   **Strict Governance:** Updated `agent_framework.md` to strictly forbid manual editing of `tools/fill_l10n.py`.
    *   **Programmatic Mapping:** Integrated `MasterMappingTool` into `l10n_tool.py` to allow safe, regex-based updates to the mapping dictionaries.
3. **Search & OCR Excellence:**
    *   **Critical Fix:** Resolved a deep database bug where the `IN` operator was unhandled, causing search results to include all documents. High-precision search (e.g., "Reichelt") now works correctly.
    *   **Force OCR Feature:** Implemented "Force OCR / Searchable PDF" in the document list. This allows users to manually trigger OCR for scanned PDFs, converting them into searchable (Sandwich) versions and enabling hit navigation in the PDF viewer.
    *   **Immediate Cache:** Searchable text is now cached immediately upon ingestion/processing to ensure real-time search availability.
4. **German Terminology Refinement:**
    *   **No Parentheses:** Removed all technical/tautological parentheses (e.g., "(Reset)", "(Console)").
    *   **Grammar Alignment:** Moved away from English-style Title Case to correct German capitalization (Satzanfang groß, Adjektive klein).
    *   **Key Results:** 
        - "Inbox" -> "Unbearbeitete Dokumente"
        - "Total Documents" -> "Belege gesamt"
        - "Purge All Data" -> "alle Daten zurücksetzen"
5. **Shortcut Integrity:**
    *   Resolved all shortcut collisions (`&`) in the main menu caused by longer German translations (e.g., A&bläufe vs &Ansicht).
    *   Fixed ampersand escaping in labels (e.g., "Bezahlt && Archiv").
6. **Logging & Hardware Resilience (Phase 210):**
    *   **High-Detail Logging:** All logs now include filename and line numbers (e.g., `core/logger.py:45`).
    *   **Silent Exception Tracking:** Introduced `get_silent_logger()` for monitoring previously hidden errors.
    *   **Graceful Hardware Handling:** Scanner functionality is now dynamically hidden if SANE is missing, instead of crashing or logging in German.

---

## **Strict Implementation Rules**
> [!DANGER]
> **NO LEGACY SUPPORT:** Legacy code path support is strictly forbidden.
> **DYNAMIC UI:** Never use `setFixedWidth()` on labels/buttons. Use `padding` and `setMinimumWidth()`.
> **SHORTCUTS:** A `&` in the source string REQUIRES a shortcut in the translation. No `&` in source means ALL `&` in translation must be `&&`.
> **L10N GOVERNANCE:** Never edit `tools/fill_l10n.py` manually. Always use `tools/l10n_tool.py change`.
> **STRICT ENGLISH LOGGING:** All technical messages (logs, console, exceptions) must be in **English**. German is only for the GUI layer.
> **LOGGING SYSTEM:** Never use `print()`. Always use `core.logger`.
> **GRACEFUL DEGRADATION:** Optional hardware features (like scanning) must fail gracefully (e.g., hide menu items) instead of triggering a hard `sys.exit`.

---

## **Current Task State**
**SEARCH ENGINE: Corrected.**
- Database `IN` operator bug fixed.
- Text occurrence count refined for German localization.
- Deep search (OCR metadata + Cache) is consistent.

**GUI STABILITY: High.**
- Dashboard (Cockpit) is resilient to long localized labels.
- **Robustness:** Background worker errors are now captured and displayed as desktop notifications.
- **New Feature:** Context-menu "Force OCR" triggered via `MainWindow.reprocess_document_slot(force_ocr=True)`.

**LOCALIZATION: Updated.**
- Added translations for search counts, OCR progress, and error reporting.
- Programs: `pylupdate6`, `fill_l10n.py`, `lrelease` sequence verified.

**NEXT STEP: Implementation of retranslate_ui in the remaining viewer widgets (PDF Viewer, Splitter Strip).**

---

## **Environment Details**
*   **Core:** Python 3.12+, PyQt6.
*   **l10n Tooling:** `tools/l10n_tool.py` (with MasterMappingTool), `pylupdate6`, `lrelease`.
*   **Testing:** `pytest` with `pytest-qt`.

---
*End of Handover Documentation*
