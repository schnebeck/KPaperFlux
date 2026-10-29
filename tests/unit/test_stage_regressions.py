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




def test_stage_2_renders_requested_vision_page(two_page_pdf: Path) -> None:
    from core.ai.stage2 import Stage2Processor

    client = MagicMock()
    client.generate_json.return_value = {"meta_header": {}, "bodies": {}}
    config = MagicMock()
    config.get_ai_retries.return_value = 0
    config.get_private_profile_json.return_value = "{}"
    config.get_business_profile_json.return_value = "{}"
    processor = Stage2Processor(client, config)

    with patch("core.utils.zugferd_extractor.ZugferdExtractor.extract_from_pdf", return_value=None):
        processor.run_stage_2(["second page"], {"type_tags": ["OTHER"]}, {}, pdf_path=str(two_page_pdf), vision_page_index=1)

    images = client.generate_json.call_args[1]["images"]
    assert len(images) == 1
    assert images[0]["page_index"] == 1


