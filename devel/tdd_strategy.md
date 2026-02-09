# **TDD Strategy: KPaperFlux**

**Frameworks:** pytest, pytest-qt, unittest.mock

## **1. Philosophy: Red-Green-Refactor**

No production code should be written unless there is a failing test that requires it.

1.  **RED:** Write a test for the feature. It must fail (e.g., `AssertionError` or `ImportError`).
2.  **GREEN:** Implement the minimal code necessary to make the test pass.
3.  **REFACTOR:** Optimize the code without changing its behavior.

## **2. Architecture-Specific Testing**

### **Model (Logic -> Unit Tests)**
*   **Test Focus:** Data integrity, file system operations, SQL logic, serialization.
*   **Hardware:** Scanners and External APIs (Google Gemini) are always mocked.

### **Controller (Flow -> Mock Tests)**
*   **Test Focus:** Does the controller respond correctly to signals? Does it orchestrate models in the right order?
*   **Mocking:** View and Model are mocked to focus solely on the sequence and flow of operations.

### **View (GUI -> pytest-qt)**
*   **Test Focus:** Widget existence, signal connections, UI state reflection.
*   **Tool:** `pytest-qt` (`qtbot`) simulates user interactions.

## **3. Test Suite Maintenance & Quality**

*   **Strict API Alignment**: Always adapt tests to the *current* API. Do **not** modify core code to support legacy test patterns or outdated API calls.
*   **Core Integrity**: Changes to core code to make tests pass must address **real bugs**. Never introduce hacks or support for legacy code just to satisfy a test.
*   **Refactoring Workflow**: To fix a failing test, first adapt the test code to the current API/Intent, then verify the program against the corrected test.
*   **Aggressive Cleanup**: Remove development-oriented or redundant tests that no longer serve a clear purpose or have been superseded by better coverage.

## **4. Unit Test Generation**

For every logic block or function you review/refactor:
1.  **Testability:** Ensure the code is written in a way that is easy to test (Dependency Injection where needed).
2.  **Test Stubs:** Generate **pytest stubs** for the code.
    *   Tests should cover the "Happy Path" (expected behavior).
    *   Tests should cover at least one "Edge Case" or error condition.

## **5. Mocking Rules**

### **Scanner (SANE)**
Tests must never attempt to access real hardware.
*   Use `unittest.mock.patch` or wrapper classes.
*   Simulate scan results by loading test images from `tests/resources/`.

### **Google AI**
Tests must not incur costs or require a network connection.
*   Mock the response of `GenerativeModel.generate_content`.
*   Return static JSON responses structured according to the current Stage 1/Stage 2 schemas.
