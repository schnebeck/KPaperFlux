# KPaperFlux: Strategic Evaluation & Reporting Concept

**Date:** 2026-02-01
**Status:** Planning / Architecture Review (Post-Refactoring v2.0)

## 1. Status Quo: The Modernized Foundation

Following a successful refactoring, KPaperFlux has reached a new technological tier. The key achievements are:

*   **Schema-less Metadata (JSON-First):** Moving away from rigid SQL columns (`doc_date`, `sender`, `amount`) towards a dynamic `semantic_data` JSON block allows for capturing information with any level of depth without requiring database migrations.
*   **AI Resilience:** Implementation of "Self-Correction" logic (Logical Retries with Prompt-Strengthening). The AI learns from JSON syntax errors and corrects itself automatically.
*   **Efficient Pipeline:**
    *   **Stage 1.5 (Visual Audit):** Focus on forensics (stamps, signatures, integrity).
    *   **Stage 2 (Semantics):** Full extraction of financial data and cross-page text repair.
*   **Stable UI:** All components (List View, Metadata Editor, Duplicate Check) have been successfully synchronized with the new architecture.

---

## 2. The Vision: From Data Grave to Knowledge Manager

The goal is now to leverage the "treasure" of extracted data. Reporting in this context is not just a list, but an **interpretative layer**.

### A. Financial Intelligence & Reporting (Mandatory)
*   **Finance Hub:** Aggregation of `amount` values over custom time periods.
*   **Tax Preparation:** Automated export (CSV/ZIP) for tax consultants, grouped by categories and tax rates.
*   **Expense Dashboard:** Visualization of cash flow and burn rates (e.g., "Software Subscriptions", "Insurance").

### B. Process Management & Workflow (Dynamics)
*   **Inbox Zero:** Using status states (`NEW`, `PAID`, `TO_PAY`) to manage the bureaucracy workflow.
*   **Deadline Monitoring:** Automatic calculation of due dates (document date + n days) with visual warning signals (traffic light system) in the UI.

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

### Phase 3: Workflow & Quality
*   Introduction of the **Anomaly Checker** (warning on price deviations).
*   Implementation of **Smart Folder Export** (physical sorting on HDD based on metadata).

---

## 5. Conclusion
KPaperFlux is now transitioning from the **Data Acquisition** phase into the **Data Utilization** phase. The architectural decision for JSON metadata is proving to be the decisive accelerator, as complex reports can operate flexibly on the `semantic_data` layer.
