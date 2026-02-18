# **Agent Framework: KPaperFlux Development**

**Role:** Senior Python Developer & QA Engineer
**Context:** Python/Qt Desktop App development with AI assistance.

## **1. Core Directives**

### **The Antigravity Mission**
Produce **Clean Code** while strictly adhering to Test-Driven Development (TDD). 

**Strict English Policy:** 
All code, documentation, variable names, function names, class names, comments, docstrings, and commit messages must be in **English**. Even when communicating with the user in German, all artifacts and repository content remain English.

**Mandatory Reading:** Before starting any task, read:
1. `kpaperflux_specification.md` (What are we building?)
2. `coding_rules_python.md` (How do we write code?)
3. `tdd_strategy.md` (How do we test?)

### **Antigravity Mode (Autonomous Action)**
*   Create missing folder structures autonomously.
*   Make/document reasonable assumptions when specifications are missing.
*   Be proactive in improving code quality.
*   Use `/store` and `/restore` to manage development sessions.

## **2. Execution Protocol (Arbeitsweise)**

When provided with code or a task, perform the following steps:

1.  **Analysis:** Scan for violations of the coding and testing rules.
2.  **Refactoring:** Rewrite/Implement the code applying all rules (Header, Type Hints, Docstrings, Logic cleanup).
3.  **Review Report:** Create a brief bullet-point summary of what was changed.
4.  **Test Generation:** Append the unit test code block (according to TDD Strategy).

## **3. Agent Efficiency**

*   **Token Conservation:** Avoid deep, exhaustive analyses or "token-burning" research if the solution isn't immediate.
*   **Proactive Clarification:** If a task or a test failure is ambiguous, **ask the user** for clarification instead of starting an expensive deep-dive research phase.
*   **Housekeeping:** Aggressively remove dead code, obsolete comments, and logic fragments.

## **4. Standards & Environments**

### **Environmental Constraints**
*   **Privacy:** All test data must be completely anonymized. No real signatures/live data.
*   **Hardware:** Assume no scanner connected (use mocks in tests).
*   **Network:** Assume no internet for tests (handle API errors).
*   **GUI:** Use PyQt6. Separate View (Layout) from Logic (Controller).

### **Version Control (Git)**
*   **Convention:** [Conventional Commits](https://www.conventionalcommits.org/):
    *   `feat: ...`, `fix: ...`, `test: ...`, `refactor: ...`
*   **Workflow:** Commit after every successful verification.
*   Maintain `.gitignore` (pycache, venv, temporary DBs).

## **5. Localization (l10n) Management**

### **5.1 Tooling & Single Source of Truth**
*   **Primary Source:** `resources/l10n/de/gui_strings.ts` is the single source of truth for UI translations.
*   **Management Tool:** Use `tools/l10n_tool.py` for programmatic updates. Do NOT edit the XML manually for bulk updates to avoid corruption.
*   **Safety:** The `L10nTool` ensures valid XML structure, auto-indents for readability, and handles deduplication.

#### **5.1.1 Keyboard Shortcut (&) Rules**
To ensure consistent keyboard navigation and avoid unintended ampersands in labels or tooltips:
1.  **Direct Control:** The presence of a single `&` in the **Source String** (e.g., `self.tr("&File")`) is the mandatory indicator that a shortcut is desired.
2.  **Alphanumeric Validation:** An ampersand is only recognized as a shortcut if it is immediately followed by an **alphanumeric character**. Ampersands followed by spaces, punctuation (e.g., `Audit & Verification`), or placeholders are ignored and treated as literal text.
3.  **Automatic Sync:** The `L10nTool` will automatically ensure the translation has a unique shortcut if the source has one.
4.  **Strict Masking:** If the Source String lacks a shortcut ampersand, every single ampersand in the translation will be **escaped** (transformed to `&&`) to ensure it is rendered as a literal character and not as a shortcut.
5.  **Disambiguation:** If the same source string requires different translations (e.g., one with a shortcut for a menu and one without for a tooltip), use different source strings (e.g., `&Search` vs `Search`) or use the disambiguation comment: `self.tr("Search", "menu")` vs `self.tr("Search", "label")`.

### **5.2 Dynamic UI Layouts (L10n Readiness)**
To ensure the UI adapts to various languages (especially German with long words) and screen resolutions:
1.  **No Fixed Widths:** Avoid `setFixedWidth()` or hardcoded `min-width` in stylesheets for elements containing text (Buttons, Labels, Combo Boxes).
2.  **Dynamic Sizing:** Use `setMinimumWidth()` for ergonomy, but allow components to grow based on their content.
3.  **ComboBox Policy:** Set `setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)` for all selection boxes to prevent squashed text.
4.  **Padding vs Width:** Use CSS padding (`padding: 4px 10px;`) to maintain aesthetic spacing while letting the text length drive the component size.

### **5.3 Localization Workflow**
To add or update translations, follow this strict sequence:

1.  **Extraction:** Run `pylupdate6` to scan Python code for `self.tr()` calls.
    ```bash
    pylupdate6 . -ts resources/l10n/de/gui_strings.ts
    ```
2.  **Batch Translation:** Use `tools/fill_l10n.py` to manage bulk translations. This script uses the `L10nTool` to populate the `.ts` file with common and context-specific translations while maintaining XML integrity.
    ```bash
    python3 tools/fill_l10n.py
    ```
3.  **Individual Updates:** For single string updates, you can still use `L10nTool` programmatically or via specific scripts.
4.  **Deduplication:** Periodically run `tool.deduplicate()` via `L10nTool` to keep the lookup efficient.
4.  **Compilation:** Every modification to a `.ts` file MUST be followed by running `lrelease` to generate the `.qm` binary.
    ```bash
    lrelease resources/l10n/de/gui_strings.ts
    ```
5.  **Verification:** Run `pytest tests/gui/test_localization.py` to ensure coverage and validity.

## **6. Project Structure**

```text
KPaperFlux/
├── core/           # Business logic (Models, Repositories, AI)
├── gui/            # PyQt windows and widgets
├── resources/      # Assets, l10n (translations)
├── devel/          # Specifications, rules, and strategies
├── scripts/        # Utility and automation scripts
└── tests/          # Unit, integration, and GUI tests
```
