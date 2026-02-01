# **TDD Strategy: KPaperFlux**

**Frameworks:** pytest, pytest-qt, unittest.mock

## **0. Data Privacy**

*   All test data must be completely anonymized!
*   Real signatures or live data from production sets are strictly forbidden in code, tests, or documentation.

## **1. Philosophy: Red-Green-Refactor**

No production code should be written unless there is a failing test that requires it.

1.  **RED:** Write a test for the feature. It must fail (e.g., `AssertionError` or `ImportError`).
2.  **GREEN:** Implement the minimal code necessary to make the test pass.
3.  **REFACTOR:** Optimize the code without changing its behavior.

## **2. Architecture (MVC Pattern)**

### **Model (Logic -> Unit Tests)**
*   **Classes:** `DocumentVault`, `PipelineProcessor`, `DatabaseManager`, `LogicalRepository`, `PhysicalRepository`.
*   **Test Focus:** Data integrity, file system operations, SQL logic, serialization.
*   **Hardware:** Scanners and External APIs (Google Gemini) are always mocked here.

### **Controller (Flow -> Mock Tests)**
*   **Classes:** `CanonizerService`, `QueueManager`.
*   **Test Focus:** Does the controller respond correctly to signals? Does it orchestrate models in the right order?
*   **Mocking:** View and Model are mocked to focus solely on the sequence and flow of operations.

### **View (GUI -> pytest-qt)**
*   **Classes:** `MainWindow`, `ResultListWidget`, `MetadataEditor`.
*   **Test Focus:** Do buttons exist? Are signals connected correctly? Does the UI reflect model changes?
*   **Tool:** `pytest-qt` (`qtbot`) simulates user interactions.

## **3. Mocking Rules**

### **Scanner (SANE)**
Tests must never attempt to access real hardware.
*   Use `unittest.mock.patch('sane.init')` or wrapper classes.
*   Simulate scan results by loading test images from `tests/resources/`.

### **Google AI**
Tests must not incur costs or require a network connection.
*   Mock the response of `generativeai.GenerativeModel.generate_content` and related methods in `AIAnalyzer`.
*   Return static JSON responses structured according to the current Stage 1/Stage 2 schemas.

## **4. Directory Structure**

```text
KPaperFlux/
├── core/           # Business logic (Models, Repositories, AI)
├── gui/            # PyQt windows and widgets
└── tests/
    ├── unit/       # Fast tests (Model/Logic)
    ├── integration/# Tests with real (temp) DB or multi-component flow
    └── gui/        # Functional tests for UI elements
```
