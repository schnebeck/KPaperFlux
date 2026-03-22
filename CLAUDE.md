# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**KPaperFlux** is a PyQt6 desktop application for intelligent document management (DMS) on KDE Plasma. It processes physical and digital documents into structured "digital twins" with AI-powered semantic extraction, forensic analysis, and European financial compliance (ZUGFeRD 2.2 / EN 16931).

## Development Commands

**Setup:**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Run application:**
```bash
python main.py
```

**Run all tests:**
```bash
pytest
```

**Run a single test file:**
```bash
pytest tests/unit/test_environment.py -v
```

**Run a single test function:**
```bash
pytest tests/gui/test_batch_tagging.py::test_batch_tagging_applies_tags -v
```

**Run intensive integration tests:**
```bash
pytest --level2
```

**Update translations (after adding/changing GUI strings):**
```bash
pylupdate6 . -ts resources/l10n/de/gui_strings.ts
python3 tools/fill_l10n.py
lrelease resources/l10n/de/gui_strings.ts -qm resources/l10n/de/gui_strings.qm
# Or use the script:
./scripts/update_translations.sh
```

## Architecture

### Layer Structure

```
core/       — Business logic, domain models, data access (no GUI imports)
gui/        — PyQt6 views and controllers (imports from core/)
plugins/    — Workflow automation plugins (hybrid_assembler, order_collection_linker)
tests/      — pytest + pytest-qt test suite
resources/  — Icons, l10n .ts/.qm files, config templates
devel/      — Developer specifications and coding rules
```

### Core Data Model (Three-Layer)

Documents exist as three distinct objects managed through `core/repositories/`:
- **PhysicalDocument** — raw file on disk (UUID-based path in vault)
- **VirtualDocument** — processing state, pipeline stage, metadata
- **SemanticDocument** — extracted structured data (amounts, dates, parties, ZUGFeRD fields)

### Processing Pipeline (`core/pipeline.py`)

Multi-stage ingestion controlled by `PipelineState`:
1. **Stage 0** — Ingestion, PDF splitting, vault storage (WORM — files never modified after write)
2. **Stage 1 (Adaptive)** — AI classification via Google Gemini with pre-flight modes: `SANDWICH`, `HEADER_SCAN`, `FULL_READ`
3. **Stage 1.5** — Visual Audit (`core/visual_auditor.py`): forensic detection of stamps, signatures, handwriting
4. **Stage 2** — Semantic extraction to JSON, ZUGFeRD/EN 16931 compliance mapping

### Key Modules

| File | Role |
|------|------|
| `core/database.py` | SQLite + FTS5 full-text search, schema migrations |
| `core/vault.py` | UUID-based immutable file storage |
| `core/ai_analyzer.py` | Google Gemini API integration |
| `core/semantic_translator.py` | ZUGFeRD / EN 16931 field extraction |
| `core/exporters/` | CSV, PDF report, ZIP export |
| `gui/main_window.py` | Application shell and signal routing |
| `gui/metadata_editor.py` | Tabbed AI result editor with dynamic tab visibility |
| `gui/document_list.py` | Filterable/searchable document table |
| `gui/reporting.py` | Dynamic reporting and analytics UI |

### Workflow System

The workflow system is split across two concerns — **definition** and **execution**:

- **Definition** (`gui/workflow_manager.py` → `WorkflowManagerWidget`): The "Ablaufeditor" tab lets the user create/edit state-machine rules (states, transitions, conditions, trigger tags). Rules are persisted as JSON in `resources/workflows/`. The dashboard tab shows live stats per rule.
- **Execution** (`gui/widgets/workflow_controls.py` → `WorkflowControlsWidget`): Embedded in the MetadataEditor. When a document is opened, if its `type_tags` match a rule's `triggers.type_tags`, the rule is auto-assigned and transition buttons appear. Clicking a button calls `WorkflowInfo.apply_transition()` and saves the new state to `semantic_data.workflow.current_step` in the DB.
- **Data model**: `core/workflow.py` — `WorkflowRule`, `WorkflowState`, `WorkflowTransition`, `WorkflowEngine`, `WorkflowRuleRegistry` (singleton). `core/models/semantic.py` — `WorkflowInfo` stores `rule_id`, `current_step`, `history`.
- **Navigation**: `WorkflowManagerWidget.navigation_requested` signal is connected to `main_window.navigate_to_list_filter()`. Emitting `{"query": {...}, "label": "..."}` switches the Explorer to a filtered view.

### Plugin System

Plugins in `plugins/` implement a defined interface and are loaded at runtime. Each plugin handles specific document workflow automation (e.g., linking orders to delivery notes).

## Coding Rules

All rules are fully specified in `devel/coding_rules_python.md`. Key constraints:

- **All code, comments, variable names, and commit messages must be in English**
- **Type hints are mandatory** on every function signature
- **Never use bare `except:`** — always catch specific exceptions. The quality gate test (`tests/test_code_quality.py`) will fail the build if silent exception handlers are found.
- **All user-facing GUI strings must use `self.tr("...")`** — never hardcode display strings
- **For parameterized tr() strings**, use positional placeholders: `self.tr("File %s not found") % filename` (not f-strings inside `tr()`)
- **Use f-strings** for all other string formatting
- **Use pathlib** instead of `os.path`
- **No legacy compatibility branches** — migrate data via isolated scripts, then delete old paths

### File Header

Every new Python file must begin with:
```python
"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           [filename]
Version:        [version]
Producer:       thorsten.schnebeck@gmx.net
Generator:      [tool used]
Description:    [concise description]
------------------------------------------------------------------------------
"""
```

## Testing Conventions

- `tests/conftest.py` forces English locale for all tests to prevent l10n flakiness
- GUI tests use `qtbot` (pytest-qt) for event simulation — no real modal dialogs
- Google Gemini API and SANE scanner hardware are always mocked in tests
- `level2` marker is for intensive integration tests, excluded from default runs
- The `tests/test_code_quality.py` quality gate is part of the standard test run

## Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `test:`, `refactor:`, `chore:`, `docs:`
