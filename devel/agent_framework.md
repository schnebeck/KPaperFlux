# **Agent Framework: KPaperFlux Development**

**Role:** Senior Python Developer & QA Engineer
**Context:** Python/Qt Desktop App development with AI assistance.

## **1. Core Directives**

### **The Antigravity Mission**
Produce **Clean Code** while strictly adhering to Test-Driven Development (TDD). 

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

## **5. Project Structure**

```text
KPaperFlux/
├── core/           # Business logic (Models, Repositories, AI)
├── gui/            # PyQt windows and widgets
├── resources/      # Assets, l10n (translations)
├── devel/          # Specifications, rules, and strategies
├── scripts/        # Utility and automation scripts
└── tests/          # Unit, integration, and GUI tests
```
