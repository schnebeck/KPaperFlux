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
    *   **CLI 'change' command:** Added a CLI interface to `l10n_tool.py` for automated updates: `python3 l10n_tool.py change --src "Source" --trans "Target" --sync`.
3. **German Terminology Refinement:**
    *   **No Parentheses:** Removed all technical/tautological parentheses (e.g., "(Reset)", "(Console)").
    *   **Grammar Alignment:** Moved away from English-style Title Case to correct German capitalization (Satzanfang groß, Adjektive klein).
    *   **Key Results:** 
        - "Inbox" -> "Unbearbeitete Dokumente"
        - "Total Documents" -> "Belege gesamt"
        - "Purge All Data" -> "alle Daten zurücksetzen"
4. **Shortcut Integrity:**
    *   Resolved all shortcut collisions (`&`) in the main menu caused by longer German translations (e.g., A&bläufe vs &Ansicht).
    *   Fixed ampersand escaping in labels (e.g., "Bezahlt && Archiv").

---

## **Strict Implementation Rules**
> [!DANGER]
> **NO LEGACY SUPPORT:** Legacy code path support is strictly forbidden.
> **DYNAMIC UI:** Never use `setFixedWidth()` on labels/buttons. Use `padding` and `setMinimumWidth()`.
> **SHORTCUTS:** A `&` in the source string REQUIRES a shortcut in the translation. No `&` in source means ALL `&` in translation must be `&&`.
> **L10N GOVERNANCE:** Never edit `tools/fill_l10n.py` manually. Always use `tools/l10n_tool.py change`.
> **TDD FIRST:** All new features or bugfixes MUST be accompanied by/verified by a test in `tests/`.

---

## **Current Task State**
**GUI STABILITY: High.**
- Dashboard (Cockpit) is resilient to long localized labels.
- Toolbar and Menus are fully localized and shortcut-safe.
- **Test Isolation:** All configuration-related tests now use `profile="test"`, ensuring production settings (`~/.config/kpaperflux/`) are protected during test runs.

**LOCALIZATION: Complete for Core Features.**
- The "Perfect Terminology" phase is complete.
- Management tools (`l10n_tool.py`) are robust and tested.

**AI BACKEND: Modernized.**
- **Baseline:** Default model updated to `gemini-2.5-flash`.
- **Lifecycle:** 1.5 and 2.0 series models are classified as "legacy" and will trigger automatic migration to the latest stable default.
- **Provider:** Running on a Gemini 3-flash based infrastructure.

**NEXT STEP: Implementation of retranslate_ui in the remaining viewer widgets (PDF Viewer, Splitter Strip).**

---

## **Environment Details**
*   **Core:** Python 3.12+, PyQt6.
*   **l10n Tooling:** `tools/l10n_tool.py` (with MasterMappingTool), `pylupdate6`, `lrelease`.
*   **Testing:** `pytest` with `pytest-qt`.

---
*End of Handover Documentation*
