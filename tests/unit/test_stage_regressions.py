"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_stage_regressions.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Regression tests for the pre-flight prompt schema, the
                Stage 1.5 page separation and the Stage 1.5 hold handling.
------------------------------------------------------------------------------
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from core.ai import prompts
from core.visual_auditor import VisualAuditor


def test_preflight_prompt_contains_schema_keys() -> None:
    prompt = prompts.PROMPT_STAGE_1_0_PREFLIGHT.format(content="Rechnung")
    for key in ("primary_type", "is_hybrid_suspicion", "looks_like_stack", "confidence"):
        assert f'"{key}"' in prompt
    assert "GROUNDING RULES" in prompt


def test_classification_prompt_contains_document_continuity_rule() -> None:
    prompt = prompts.PROMPT_STAGE_1_1_CLASSIFICATION.format(identity_json_str="{}", mode="FULL_READ_MODE", analysis_text="x")
    assert "6. **Document Continuity (Annexes, Reports & 'OTHER' Sink):**" in prompt
    assert "The 'OTHER' Sink" in prompt
    assert "7. **GROUNDEDNESS & UNCERTAINTY:**" in prompt
    assert "\n9. \n" not in prompt


def test_split_prompt_has_allowed_types_heading() -> None:
    prompt = prompts.PROMPT_STAGE_1_2_SPLIT.format(structural_hints="", allowed_types_str="INVOICE, OTHER", text_content="x")
    assert "### ALLOWED TYPES\nINVOICE, OTHER" in prompt
    assert "### DATA INTEGRITY RULES:" in prompt


def test_stage_2_master_prompt_names_extraction_target() -> None:
    from core.ai.stage2 import Stage2Processor

    client = MagicMock()
    client.generate_json.return_value = {"meta_header": {}, "bodies": {}}
    config = MagicMock()
    config.get_ai_retries.return_value = 0
    config.get_private_profile_json.return_value = "{}"
    config.get_business_profile_json.return_value = "{}"
    Stage2Processor(client, config).run_stage_2(["page text"], {"type_tags": ["INVOICE"]}, {})

    prompt = client.generate_json.call_args[0][0]
    assert "### 4. EXTRACTION TARGET: INVOICE" in prompt
    assert "- **GROUNDING & DATA INTEGRITY:**" in prompt
    assert prompt.index("### 4. EXTRACTION TARGET") < prompt.index("GROUNDING & DATA INTEGRITY")


@pytest.fixture
def two_page_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "two.pdf"
    doc = fitz.open()
    for text in ("first page", "second page"):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()
    return path


def test_visual_auditor_uses_first_page_only(two_page_pdf: Path) -> None:
    auditor = VisualAuditor(MagicMock())
    data = auditor.generate_audit_images_and_text(str(two_page_pdf), "STAMP_ONLY", text_content="OCR P1\fOCR P2", target_pages=[1, 2])
    assert data["page1_text"] == "OCR P1"
    assert len(data["images"]) == 1


def test_stage_1_5_returns_none_when_ai_fails(two_page_pdf: Path) -> None:
    ai = MagicMock()
    ai._generate_json.return_value = None
    auditor = VisualAuditor(ai)
    result = auditor.run_stage_1_5(two_page_pdf, "doc", {"detected_entities": [{"entity_type": "INVOICE"}]}, text_content="a\fb")
    assert result is None


def test_stage_1_5_not_required_returns_meta_none(two_page_pdf: Path) -> None:
    auditor = VisualAuditor(MagicMock())
    result = auditor.run_stage_1_5(two_page_pdf, "doc", {"detected_entities": [{"entity_type": "PAYSLIP"}]})
    assert result == {"meta_mode": "NONE"}


def test_canonizer_passes_form_feed_pages_and_holds_on_stage_1_5_failure() -> None:
    from core.canonizer import CanonizerService
    from core.models.virtual import DocumentStatus, SourceReference, VirtualDocument

    analyzer = MagicMock()
    analyzer.run_stage_1_adaptive.return_value = {"detected_entities": [{"type_tags": ["INVOICE"], "page_indices": [1, 2]}]}
    logical_repo, physical_repo = MagicMock(), MagicMock()
    phys = MagicMock()
    phys.file_path = "/nonexistent.pdf"
    phys.raw_ocr_data = json.dumps({"1": "Page 1 Text", "2": "Page 2 Text"})
    physical_repo.get_by_uuid.return_value = phys

    service = CanonizerService(MagicMock(), analyzer, physical_repo=physical_repo, logical_repo=logical_repo)
    v_doc = VirtualDocument(uuid="doc-1", source_mapping=[SourceReference(file_uuid="p", pages=[1, 2])], status="NEW", type_tags=["INVOICE"])

    with patch.object(service.visual_auditor, "run_stage_1_5", return_value=None) as mock_audit, \
         patch.object(service, "_atomic_transition", return_value=True), \
         patch.object(service, "_detect_zugferd_type_tags", return_value=None):
        assert service.process_virtual_document(v_doc) is False

    assert mock_audit.call_args[1]["text_content"] == "Page 1 Text\fPage 2 Text"
    assert logical_repo.save.call_args[0][0].status == DocumentStatus.STAGE1_5_HOLD
    analyzer.run_stage_2.assert_not_called()
