# KPaperFlux: Strategic Evaluation & Roadmap

**Date:** 2026-03-27
**Status:** Workflow Engine Mature — Transitioning to Document Intelligence & Deadline Management

---

## 1. Status Quo: What Is Done

### Core Infrastructure (Stable)
- **Three-Layer Document Model:** `PhysicalDocument` (vault/WORM) → `VirtualDocument` (state/pipeline) → `SemanticDocument` (extracted JSON) — proven and stable.
- **Multi-Stage Pipeline (Stage 0–2):** Ingestion, PDF splitting, adaptive AI preflight (`SANDWICH` / `HEADER_SCAN` / `FULL_READ`), forensic visual audit (Stage 1.5), semantic extraction (Stage 2).
- **Local AI Sovereignty:** Multi-backend support — Gemini, OpenAI, Anthropic, Ollama. 100% local processing possible.
- **SQLite + FTS5:** Full-text search, semantic JSON querying via `json_extract` / `json_each`, schema migrations, virtual columns.
- **Vault (WORM):** UUID-based immutable file storage. Files are never modified after write.
- **404 unit and GUI tests**, single remaining TODO in codebase. Quality gate enforced via `test_code_quality.py`.

### Reporting & Analytics (Stable)
- **Reporting Canvas (WYSIWYG):** Reorderable, annotatable report components (charts, tables, text). Real-time drag-and-drop layout.
- **High-Fidelity PDF Export:** Exact canvas layout preserved in export.
- **Charting:** `PieChartWidget`, `BarChartWidget`, `LineChartWidget` with sync-zooming.
- **Generalized Grouping Engine:** Reports group by arbitrary semantic fields, not just hardcoded categories.
- **Multi-Format Export:** CSV, ZIP, PDF. Stream-based (low memory footprint for 10k+ records).
- **Internationalized PDF Reports:** i18n via Qt `.ts` / `.qm` pipeline, German locale fully translated.

### Workflow Engine (Mature)
- **Generic Finite State Machine:** JSON-defined rules (`resources/workflows/`), states, transitions, conditions, triggers.
- **Multi-Workflow per Document:** A document can simultaneously carry multiple active workflows (e.g. `INVOICE` + `ORDER_CONFIRMATION`). `SemanticExtraction.workflows: Dict[str, WorkflowInfo]` keyed by rule ID.
- **Workflow Canvas:** Interactive run-mode graph with clickable state nodes, dashed hover-ring affordance, color-coded states (current / available / visited / blocked / final-ok / final-error), auto-transitions, condition tooltips.
- **Workflow Dashboard:** Per-rule document counts with live DB queries.
- **Workflow Summary Tab:** Per-document active workflows with step counts in `MetadataEditor`.
- **WorkflowEngine conditions:** `required_fields`, `conditions` (field/op/value), auto-transitions.
- **Two bundled workflows:** `invoice_standard`, `smart_dunning`.

### GiroCode & Payment (Stable)
- **EPC QR Code generation** (`core/utils/girocode.py`) fully wired into the payment tab of `MetadataEditor` with live-refresh on field changes.

### Forensic / Hybrid PDF (Partial)
- `HybridEngine`, `ForegroundDetector`, forensic ink extraction: complete.
- `ZugferdExtractor` (`core/utils/zugferd_extractor.py`): complete and tested.
- `PAdES` signature detection: complete.
- Immutability protection (UI locks, pipeline routing): complete.
- **Missing:** ZUGFeRD/PAdES data is NOT yet injected into `SemanticExtraction` before the AI call (Stage 0.5). See Section 3.

### Plugin System
- Interface defined, `hybrid_assembler` and `order_collection_linker` implemented.
- Runtime loading at startup. No hot-reload, no settings-UI for installed plugins.

---

## 2. Known Architectural Weaknesses

### 1. `main_window.py` is a God-Object (2600+ lines)
Directly coordinates signals between all subsystems. Risk of circular dependency growth as the project scales. Mitigation: introduce a central `ApplicationController` or thin event-bus layer for cross-subsystem signals.

### 2. Pipeline has no real cancellation protocol
`PipelineProcessor.process_document()` is a single synchronous call. `terminate_activity()` is a soft-stop flag, not a true cooperative cancellation. Large batches block until the current document finishes. Mitigation: structured cancellation tokens per stage.

### 3. `core/database.py` is monolithic (1700+ lines)
Schema migrations, query builder, virtual column definitions, and `json_each` special-case handlers coexist in one class. `_build_where_clause()` accumulates special cases. Mitigation (future): extract a `QueryBuilder` class.

### 4. Plugin system is opaque to the user
No settings panel showing installed plugins, their version, or on/off toggle. Plugins cannot be added/removed at runtime.

---

## 3. Roadmap: Open Feature Work

### Priority 1 — ZUGFeRD Stage 0.5 Injection (High Impact)

**Problem:** `ZugferdExtractor` exists and works, but the pipeline calls the AI unconditionally. For ZUGFeRD/Factur-X PDFs, the embedded XML already contains 100% accurate structured data (amounts, dates, parties, line items). Running a full AI extraction wastes tokens and introduces potential hallucinations.

**Design:**
1. In `PipelineProcessor._run_ai_analysis()` (or a new pre-stage before it): call `ZugferdExtractor.extract(path)`.
2. If XML data is found: populate `SemanticExtraction` fields directly from XML. Set `ai_confidence = 1.0`, `source = "ZUGFERD_NATIVE"`.
3. Switch AI to **Audit Mode**: instead of full extraction, the AI only verifies visual text vs. XML data and reports discrepancies as red flags.
4. If no XML: normal AI extraction flow unchanged.

**Benefit:** Token savings ~80% for ZUGFeRD documents; zero hallucination risk on structured data.

---

### Priority 2 — Deadline Monitor / Traffic-Light in DocumentList (High Impact)

**Problem:** `due_date`, `service_period_end`, and Skonto deadlines are extracted and stored, but there is no proactive warning system. The user discovers overdue documents by accident.

**Design:**
- Add a `DeadlineMonitor` service (`core/deadline_monitor.py`) that computes urgency tiers:
  - 🔴 **Overdue** — due date in the past
  - 🟡 **Due soon** — within configurable days (default: 7)
  - 🟢 **OK** — no deadline or deadline far away
- `DocumentListWidget` gets an optional urgency column (traffic-light icon). Sortable.
- `Cockpit` gets a "Due Today / This Week" card pulling from the same monitor.
- Filter system gets a `deadline` operator (`overdue`, `due_within_N_days`).

---

### Priority 3 — PDF-Viewer Integrity Status Bar (Medium Impact)

**Problem:** `PdfViewerWidget` renders documents but communicates nothing about their forensic status. Users cannot see if a document has a verified digital signature, embedded ZUGFeRD XML, or forensic attachments.

**Design:** Slim overlay bar at the top of `PdfViewerWidget`:
- 🛡️ **Signature**: PAdES/digital signature status (verified / unverified / absent). Click → details dialog.
- ⚙️ **Data**: ZUGFeRD / EN 16931 structured data present. Click → show raw XML.
- 📎 **Attachment**: embedded original PDF or XML. Click → Save-As dialog.

Icons are greyed-out when not applicable (no visual noise for unstructured scans).

---

### Priority 4 — Saved Reports (Medium Impact)

**Problem:** Report configurations (chart selection, grouping, filters, layout order) are not persisted. Every session starts from the default state. Power users rebuild the same report repeatedly.

**Design:**
- Serialize the current report canvas state to JSON (list of component configs + layout positions).
- Store in a new `saved_reports` table in SQLite (name, json_config, created_at, last_used_at).
- `ReportingWidget` gets a "Save As..." / "Load..." toolbar button.
- Saved reports appear in a sidebar list, double-click loads them.

---

### Priority 5 — Document Reference Browser (Low Impact)

**Problem:** `DocumentReference` (order numbers, customer IDs, project IDs) is extracted into `SemanticExtraction.meta_header.references`, but there is no UI that exploits these links. A user cannot click "show all documents with Order No. 12345".

**Design:**
- In `MetadataEditor` references section: each reference value becomes a clickable chip.
- Clicking emits `navigation_requested` with a pre-built filter query `{"semantic:meta_header.references[*].ref_value": "12345"}`.
- `MainWindow` routes this to `DocumentList` filter — same mechanism as workflow navigation.

---

### Priority 6 — Plugin Settings UI (Low Impact)

- Settings dialog gets a "Plugins" tab showing: name, version, description, enabled/disabled toggle.
- Reads from `manifest.json` of each discovered plugin directory.

---

## 4. PDF Integrity & Hybrid Strategy (Reference)

KPaperFlux treats "Digital Originals" (signed, XML-enriched) and "Scanned Copies" as non-equal entities fused into a **Hybrid Truth**.

### Chain of Trust Model
- **Sacred Source:** Digitally signed (PAdES) or ZUGFeRD-XML-enriched PDFs.
- **The Hybrid:** Forensic ink (stamps, signatures) extracted from scan overlaid on the digital original.
- **Internal Linkage:** Hybrid PDF embeds the original signed PDF as an attachment — one file contains both the "Human View" and the "Legal View".

### Immutability Layer (Complete)
- `kpaperflux_immutable` protection flag prevents splitting, page deletion, and physical stamping.
- Immutable documents bypass Stage 0 splitter, proceed directly to semantic analysis.

### Standards Supported
- **ZUGFeRD 2.2 / Factur-X / EN 16931:** High-fidelity XML extraction (extractor complete; pipeline injection pending — see Priority 1).
- **PAdES:** Signature detection and preservation (complete).
- **Hybrid PDF V3:** Overlay strategy ~150KB overhead.

---

## 5. Workflow Engine: Next Steps

The engine itself is stable. Open work is at the edges:

- **Timed transitions:** Auto-escalation after N days without activity (e.g., "30 days no payment → DUNNING"). Requires a background scheduler or on-load age-check in `WorkflowEngine`.
- **External triggers:** File-system watch or webhook to advance a workflow step automatically.
- **Shared workflow templates:** Community-shareable `.json` rule files (e.g., German PKV reimbursement, DATEV export checklist). The JSON format is already self-contained and portable.
- **Workflow transition history UI:** The `WorkflowLog` history is stored per document but has no dedicated audit-trail view in the UI (only visible in raw JSON).

---

## 6. Conclusion

KPaperFlux has successfully transitioned from **Data Acquisition** to **Task-Based Knowledge Management**. The workflow engine, multi-backend AI, and forensic hybrid pipeline are production-ready. The next phase focuses on closing the gap between *data that is extracted* and *insight that is surfaced* — specifically deadline awareness, ZUGFeRD-native accuracy, and navigable document relationships.
