# KPaperFlux: Strategic Evaluation & Reporting Concept

**Date:** 2026-02-06
**Status:** Post-Clean-up & Plugin-System-Design (Phase Transition)

## 1. Status Quo: The Modernized Foundation

Following a successful refactoring, KPaperFlux has reached a new technological tier. The key achievements are:

*   **Schema-less Metadata (JSON-First):** Moving away from rigid SQL columns (`doc_date`, `sender`, `amount`) towards a dynamic `semantic_data` JSON block allows for capturing information with any level of depth without requiring database migrations.
*   **AI Resilience:** Implementation of "Self-Correction" logic (Logical Retries with Prompt-Strengthening). The AI learns from JSON syntax errors and corrects itself automatically.
*   **Efficient Pipeline:**
    *   **Stage 1.5 (Visual Audit):** Focus on forensics (stamps, signatures, integrity).
    *   **Stage 2 (Semantics):** Full extraction of financial data and cross-page text repair.
*   **Stable UI:** All components (List View, Metadata Editor, Duplicate Check) have been successfully synchronized with the new architecture.
*   **Transfer Infrastructure:** A dedicated Transfer folder for manual Import/Export has been implemented, providing a clean "Pre-Ingest" and "Post-Process" staging area.
*   **Plugin System Foundation:** A master specification for an extensible Plugin API with GUI support and specialized PDF (Hybrid/Signed) handling has been drafted.

---

## 2. The Vision: From Data Grave to Knowledge Manager

The goal is now to leverage the "treasure" of extracted data. Reporting in this context is not just a list, but an **interpretative layer**.

### A. Financial Intelligence & Reporting (Mandatory)
*   **Finance Hub:** Aggregation of `amount` values over custom time periods.
*   **Tax Preparation:** Automated export (CSV/ZIP) for tax consultants, grouped by categories and tax rates.
*   **Expense Dashboard:** Visualization of cash flow and burn rates (e.g., "Software Subscriptions", "Insurance").

### B. Process Management & Workflow (Task-Based Interaction)
*   **Generic State Machine:** Moving from a hard-coded "Processing" state to a freely-definable Workflow Engine (Finite State Machine).
*   **Inbox Zero:** Managing the bureaucracy lifecycle (e.g., `NEW` -> `VERIFIED` -> `PAID` -> `DONE`).
*   **Deadline Monitoring:** Proactive calculation of due dates and discount periods (Skonto) with a unified "Traffic Light" warning system.
*   **Dynamic UI Orchestration:** The Metadata Editor adapts its fields and buttons based on the document's current workflow step.

### C. Context & Relations (Knowledge)
*   **Knowledge Graph:** Linking documents (e.g., Quote <-> Invoice).
*   **Timeline View:** Displaying documents on a chronological axis instead of a static list.

---

## 3. Technical Pillars of `core/reporting.py`

Implementation follows modern software design patterns to guarantee scalability and maintainability.

### I. Stream-Based Processing
Instead of collecting data in RAM, we work with file streams.
*   **Advantage:** Exporting thousands of documents with minimal memory footprint.
*   **Technique:** Manual JSON/CSV stream construction directly into the file handle.

### II. Strategy Pattern (Exporter)
Decoupling the data source from the export format.
*   `CsvExporter`, `JsonExporter`, `ExcelFriendlyExporter` (using `utf-8-sig`).

### III. Aggregation Layer (Finance & Time Series)
A specialized module in the core calculates sums and groups.
*   **Input:** Filter results from the database.
*   **Output:** Aggregated data structures for charts and reports.

### IV. Data Quality Scoring
A "Watchdog" module assesses data health (Anomaly Detection).
*   **Check:** Missing mandatory fields, incorrect date formats, unusual amounts (compared to the sender's average).

---

## 4. Implementation Strategy (Phase Model)

### Phase 1: The Reporting Engine (Core)
*   Implementation of the `ReportGenerator` base class.
*   Creation of the `FinancialTimeModule` for aggregating amounts by month/tag.
*   Integration of `CsvExporter` with Excel optimization (`utf-8-sig`).

### Phase 2: Actionability (Quick Wins)
*   **GiroCode Generator:** Integration of a QR code generator (EPC standard), based on extracted IBAN/amount data from Stage 2.
*   **Dashboard Integration:** Initial graphical evaluations in the main window (bar charts for expenses).

### Phase 3: Generic Workflow Engine (State Machine)
*   **Workflow Schema:** Definition of YAML/JSON-based state machines (States, Transitions, Requirements).
*   **Shared Templates:** Library of community-driven workflows (e.g., "Health Reimbursement", "Tax Deductibles").
*   **Adaptive UI:** Dynamic button/input rendering in the Metadata Editor based on current state.

### Phase 4: Quality & Smart Exports
*   **Anomaly Checker:** Machine Learning based warning on unusual price or IBAN deviations.
*   **Smart Folder Export:** Automatic physical sorting on HDD based on finalized workflow results.

---

## 6. Infrastructure: The Generic State Machine

The core shift is from **"What is this document?"** to **"What needs to be done with this document?"**.

### I. Programmable Lifecycle
Workflows are treated as "Playbooks". A playbook defines:
1.  **Triggers:** Events that start the process (e.g., Tag `INVOICE` added).
2.  **Steps:** Specific states (e.g., `WAITING_FOR_PAYMENT`).
3.  **Requirements:** Data fields that must be filled before transitioning (e.g., `IBAN` must be valid).
4.  **Transitions:** Named actions (e.g., "Confirm Reimbursement").

### II. Community & Sharing
By decoupling the workflow logic from the Python code, users can share their "State Machines" (e.g., a specific German 'DATEV' export workflow or a complex medical reimbursement flow).

## 7. Conclusion

KPaperFlux is transitioning from **Data Acquisition** to **Task-Based Knowledge Management**. The architectural decision for JSON metadata and the new Generic State Machine allows the system to guide the user through complex bureaucratic processes, rather than just displaying data.
