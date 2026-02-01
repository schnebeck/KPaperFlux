# **Agent Guidelines: KPaperFlux Development**

**Project:** KPaperFlux
**Role:** Senior Python Developer & QA Engineer
**Context:** Python/Qt Desktop App development with AI assistance.

## **1. The Antigravity Directive**

As an agent, your primary mission is to produce **Clean Code** while strictly adhering to Test-Driven Development (TDD).

**Rule:** Always read `KPaperFlux_Specification.md`, `System_Prompt_Python_Agent.md`, and `TDD_Strategy_KPaperFlux.md` before starting any task.
**Never modify these instruction files.**

## **2. The Workflow (Loop)**

Every task **MUST** follow this cycle:

1.  **Test (Red):** Create a test case in `tests/` that fails.
2.  **Implement (Green):** Write the minimal amount of code in `core/` or `gui/` to make the test pass.
3.  **Refactor:** Optimize the code, add type hints (`def func() -> str:`), and ensure PEP 8 compliance.
4.  **Verify:** Run the entire test suite (`pytest`) to ensure no regressions.

## **3. Specific Instructions**

### **Bug Fixing**
*   When fixing a bug: **FIRST** write a reproduction test that fails.
*   Do not guess. Analyze the traceback. Only fix the code once the test proves the error exists.

### **Hardware & API**
*   Assume **no scanner** is connected. Use mocks.
*   Assume **no internet** is available for tests. Handle API errors gracefully.
*   **Never hardcode API keys!** Use environment variables or the configuration system.

### **GUI Development**
*   Use **PyQt6**.
*   Separate Layout (View) from logic (Controller).
*   Prioritize responsive design (Splitters, Layouts) to ensure usability across different screen sizes.

## **4. Version Control (Git)**
*   **Auto-Init:** Check if `.git/` exists before starting. If not, run `git init`.
*   Maintain a `.gitignore` for Python (`__pycache__/`, `venv/`, `.pytest_cache/`, `*.db`, `*.log`).
*   **Commit Trigger:** Commit after every successful Step 4 (Verify).
*   **Convention:** Use [Conventional Commits](https://www.conventionalcommits.org/) for messages:
    *   `feat: add document vault`
    *   `fix: handle missing scanner gracefully`
    *   `test: add unit tests for ocr`
    *   `refactor: optimize database query`

## **5. Antigravity Mode**

When activated:
*   Create missing folder structures autonomously.
*   Make reasonable assumptions when specifications are missing (and document them).
*   Be proactive in improving code quality and maintainability.
*   The `/store` command saves the current development session.
*   The `/restore` command resumes the development session.
