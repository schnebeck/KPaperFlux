# KPaperFlux: Strategic Evaluation & Roadmap

**Date:** 2026-03-28
**Status:** Architecture Refactoring Complete — ZUGFeRD Zero-Token Pipeline & Deadline Monitor Implemented

---

## 1. Status Quo: What Is Done

### Core Infrastructure (Stable)
- **Three-Layer Document Model:** `PhysicalDocument` (vault/WORM) → `VirtualDocument` (state/pipeline) → `SemanticDocument` (extracted JSON) — proven and stable.
- **Multi-Stage Pipeline (Stage 0–2):** Ingestion, PDF splitting, adaptive AI preflight (`SANDWICH` / `HEADER_SCAN` / `FULL_READ`), forensic visual audit (Stage 1.5), semantic extraction (Stage 2).
- **Local AI Sovereignty:** Multi-backend support — Gemini, OpenAI, Anthropic, Ollama. 100% local processing possible.
- **SQLite + FTS5:** Full-text search, semantic JSON querying via `json_extract` / `json_each`, schema migrations. `QueryBuilder` extracted into `core/query_builder.py`.
- **Vault (WORM):** UUID-based immutable file storage. Files are never modified after write.
- **476 unit and GUI tests**, zero TODOs in production code. Quality gate enforced via `test_code_quality.py`.

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

### GUI Architecture (Refactored — March 2026)
- **`DocumentActionController`** (`gui/controllers/document_action_controller.py`, 599 lines): All document operations (import, delete, reprocess, stamp, archive, purge, restore) extracted from `MainWindow`. Communicates back via signals only — no widget references.
- **`MainWindowMenuMixin`** (`gui/main_menu.py`, 501 lines): All menu bar, toolbar, tab navigation, and `retranslate_ui` logic extracted as a Python mixin.
- **`DebugController`** (`gui/controllers/debug_controller.py`, 196 lines): All debug/maintenance operations extracted from `MainWindow` into a signal-based controller.
- **`main_window.py` reduced** from 2641 → 1625 lines (−38%). Now acts as an orchestration shell only.

### Forensic / Hybrid PDF (Complete)
- `HybridEngine`, `ForegroundDetector`, forensic ink extraction: complete.
- `ZugferdExtractor` (`core/utils/zugferd_extractor.py`): complete and tested.
- `PAdES` signature detection: complete.
- Immutability protection (UI locks, pipeline routing): complete.
- **Stage 0 (ZUGFeRD TypeCode):** `Canonizer._detect_zugferd_type_tags()` reads BT-3 TypeCode from embedded XML before Stage 1. If found, `type_tags` are set from the XML (e.g. `INVOICE`, `CREDIT_NOTE`) and the Stage 1 AI classification call is skipped entirely.
- **Stage 0.5 (ZUGFeRD Finance Injection):** In `Stage2Processor.run_stage_2()`, if ZUGFeRD XML is found and `entity_type` is in `_ZUGFERD_NATIVE_TYPES` (`INVOICE`, `CREDIT_NOTE`, `RECEIPT`, `UTILITY_BILL`), `SemanticExtraction` is built directly from the XML via `_apply_zugferd_overlay()`. The AI extraction LLM call is skipped. `extraction_source = "ZUGFERD_NATIVE"`, `ai_confidence = 1.0`. Zero LLM tokens for ZUGFeRD documents.

### Deadline Monitor (New — March 2026)
- `core/deadline_monitor.py`: `UrgencyTier(IntEnum)` (OVERDUE=0, DUE_SOON=1, OK=2, NONE=3), `compute_tier()`, icon/tooltip maps.
- `DocumentListWidget`: urgency column 13 with traffic-light emoji, sortable via `Qt.ItemDataRole.UserRole`.
- `Cockpit`: two default cards — "Overdue Documents" (red) and "Due Soon" (amber) — using `expiry_date` queries.
- `FilterTokenRegistry`: `deadline` category with `expiry_date`, `due_date`, `service_period_end` tokens.
- `QueryBuilder`: `"TODAY"` relative date literal resolves to `date.today().isoformat()`.

### Plugin System
- Interface defined, `hybrid_assembler` and `order_collection_linker` implemented.
- Runtime loading at startup. No hot-reload, no settings-UI for installed plugins.

---

## 2. Known Architectural Weaknesses

### 1. `main_window.py` still coordinates too much (1625 lines)
The God-Object problem is substantially reduced but not eliminated. `MainWindow.__init__` still chains ~15 `_setup_*` calls and routes cross-subsystem signals directly. The remaining 1625 lines contain: setup helpers, signal wiring for every subsystem, search/filter coordination, splitter dialog, and scanner/cockpit integration. A central `ApplicationBus` (thin event broker) would decouple subsystems without requiring widgets to know about each other. **Risk level: medium** — the current structure is maintainable but will resist further feature additions.

### 2. `DocumentActionController` is too large (599 lines)
While a clear improvement over inline code in `MainWindow`, the controller handles 10 distinct operations. Each operation (import, delete, reprocess, stamp, archive…) has its own worker thread, signals, and error handling. As complexity grows, this class risks becoming the next God-Object. Candidate split: `ImportController`, `LifecycleController` (delete/archive/purge/restore), `ProcessingController` (reprocess/stage2/stamp).

### 3. Pipeline has no real cancellation protocol
`PipelineProcessor.process_document()` is a single synchronous call. `terminate_activity()` is a soft-stop flag, not a true cooperative cancellation. Large batches block until the current document finishes. Mitigation: structured cancellation tokens per stage.

### 4. `core/database.py` is still monolithic (1392 lines)
`QueryBuilder` was extracted into `core/query_builder.py` (354 lines), which resolved the `_build_where_clause` accumulation problem. However, schema migrations, virtual column definitions, and the hydration/repository layer still coexist in `database.py`. The `repositories/` layer (`logical_repo.py`, `physical_repo.py`) exists but is not fully used — `DatabaseManager` still performs direct hydration in many places. Full separation of concerns would require routing all reads through the repository layer.

### 5. Plugin system is opaque to the user
No settings panel showing installed plugins, their version, or on/off toggle. Plugins cannot be added/removed at runtime.

### 6. No background scheduler
Timed workflow transitions (e.g., "30 days no payment → DUNNING") and deadline monitoring both require periodic evaluation. There is no background scheduler or daemon thread. Each check currently happens only on document open or explicit user action. A lightweight scheduler (`APScheduler` or a simple `QTimer`-based interval) would enable proactive alerting.

---

## 3. Roadmap: Open Feature Work

### ~~Priority 1 — ZUGFeRD Stage 0.5 Injection~~ ✅ DONE

Implemented as **Stage 0** (TypeCode → skip Stage 1 AI) and **Stage 0.5** (XML finance injection → skip Stage 2 AI). Zero LLM tokens for all ZUGFeRD/Factur-X documents. `extraction_source = "ZUGFERD_NATIVE"`. 21 new unit tests added.

---

### ~~Priority 2 — Deadline Monitor / Traffic-Light in DocumentList~~ ✅ DONE

Implemented: `core/deadline_monitor.py` (`UrgencyTier`, `compute_tier`), urgency column in `DocumentListWidget` (sortable), two Cockpit cards (Overdue / Due Soon), `deadline` filter tokens, `TODAY` literal in `QueryBuilder`. 16 new unit tests added.

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
- **ZUGFeRD 2.2 / Factur-X / EN 16931:** High-fidelity XML extraction (complete); Stage 0 TypeCode-based classification (complete); Stage 0.5 zero-token finance injection (complete).
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

KPaperFlux has successfully completed its **architecture refactoring phase** (March 2026) and subsequently delivered two high-impact document intelligence features: `MainWindow` reduced by 38%, three controller/mixin extractions, `QueryBuilder` separation, multi-workflow model. The codebase now has **476 tests** and zero production TODOs.

**March 2026 additions:**
- **ZUGFeRD zero-token pipeline:** Stage 0 (TypeCode → skip Stage 1) + Stage 0.5 (XML injection → skip Stage 2). All ZUGFeRD documents processed with zero LLM tokens. `extraction_source` field on `SemanticExtraction` tracks data provenance.
- **Deadline Monitor:** `UrgencyTier`-based traffic-light system surfaced in document list, cockpit, and filter tokens.

The next phase focuses on:
1. **Forensic transparency** (surface signature/ZUGFeRD status directly in the PDF viewer — Priority 3)
2. **Report persistence** (save/load report canvas configurations — Priority 4)
3. **Background scheduler** (timed workflow transitions, proactive deadline alerting)
