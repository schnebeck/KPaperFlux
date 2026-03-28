"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_zugferd_stage05.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for ZUGFeRD Stage 0.5 native injection.
                Verifies that the AI LLM call is skipped when ZUGFeRD XML
                is present for eligible document types, and that extraction
                source is correctly recorded.
------------------------------------------------------------------------------
"""

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_zugferd_data() -> dict:
    """Minimal ZUGFeRD extraction dict (as returned by ZugferdExtractor)."""
    return {
        "meta_data": {
            "sender": {"name": "ACME GmbH", "street": "Musterstraße 1",
                       "zip_code": "12345", "city": "Berlin", "country": "DE",
                       "vat_id": "DE123456789", "iban": None},
            "recipient": {"name": "Kunde AG", "street": None, "zip_code": None,
                          "city": None, "country": None, "vat_id": None, "iban": None},
            "doc_number": "INV-2025-001",
            "doc_date": "2025-01-15",
        },
        "finance_data": {
            "invoice_number": "INV-2025-001",
            "invoice_date": "2025-01-15",
            "due_date": "2025-02-14",
            "currency": "EUR",
            "monetary_summation": {
                "grand_total_amount": "1190.00",
                "tax_total_amount": "190.00",
                "tax_basis_total_amount": "1000.00",
                "line_total_amount": "1000.00",
                "due_payable_amount": "1190.00",
            },
            "tax_breakdown": [
                {"tax_rate": "19", "tax_basis_amount": "1000.00",
                 "tax_amount": "190.00", "tax_type_code": "VAT",
                 "tax_category_code": "S"},
            ],
            "payment_accounts": [],
            "line_items": [],
        },
    }


def _make_stage2_processor() -> "Stage2Processor":  # noqa: F821
    """Instantiate a Stage2Processor with mocked dependencies."""
    from core.ai.stage2 import Stage2Processor

    config = MagicMock()
    config.get_ai_retries.return_value = 0
    config.get_private_profile_json.return_value = "{}"
    config.get_business_profile_json.return_value = "{}"

    client = MagicMock()
    proc = Stage2Processor.__new__(Stage2Processor)
    proc.config = config
    proc.client = client
    return proc


# ---------------------------------------------------------------------------
# Stage 0.5 — AI call skipped
# ---------------------------------------------------------------------------

class TestZugferdStage05NativeInjection:

    def test_ai_not_called_for_invoice_with_zugferd(self):
        """When ZUGFeRD XML is present for INVOICE, client.generate_json must NOT be called."""
        proc = _make_stage2_processor()
        zugferd_data = _make_zugferd_data()

        stage_1_result = {"detected_entities": [{"type_tags": ["INVOICE"]}]}
        stage_1_5_result = {}

        with patch("core.utils.zugferd_extractor.ZugferdExtractor.extract_from_pdf",
                   return_value=zugferd_data):
            result = proc.run_stage_2(
                raw_ocr_pages=["Rechnung INV-2025-001"],
                stage_1_result=stage_1_result,
                stage_1_5_result=stage_1_5_result,
                pdf_path="/tmp/test.pdf",
            )

        proc.client.generate_json.assert_not_called()
        assert result is not None

    def test_extraction_source_is_zugferd_native(self):
        """extraction_source must be 'ZUGFERD_NATIVE' when injected from XML."""
        proc = _make_stage2_processor()
        zugferd_data = _make_zugferd_data()

        stage_1_result = {"detected_entities": [{"type_tags": ["INVOICE"]}]}

        with patch("core.utils.zugferd_extractor.ZugferdExtractor.extract_from_pdf",
                   return_value=zugferd_data):
            result = proc.run_stage_2(
                raw_ocr_pages=["Rechnung"],
                stage_1_result=stage_1_result,
                stage_1_5_result={},
                pdf_path="/tmp/test.pdf",
            )

        assert result["extraction_source"] == "ZUGFERD_NATIVE"

    def test_ai_confidence_is_1_for_zugferd_native(self):
        """ai_confidence must be 1.0 for ZUGFeRD native extractions."""
        proc = _make_stage2_processor()
        zugferd_data = _make_zugferd_data()

        stage_1_result = {"detected_entities": [{"type_tags": ["INVOICE"]}]}

        with patch("core.utils.zugferd_extractor.ZugferdExtractor.extract_from_pdf",
                   return_value=zugferd_data):
            result = proc.run_stage_2(
                raw_ocr_pages=["Rechnung"],
                stage_1_result=stage_1_result,
                stage_1_5_result={},
                pdf_path="/tmp/test.pdf",
            )

        assert result["ai_confidence"] == 1.0

    def test_finance_data_populated_from_xml(self):
        """finance_body in result must contain ZUGFeRD XML data."""
        proc = _make_stage2_processor()
        zugferd_data = _make_zugferd_data()

        stage_1_result = {"detected_entities": [{"type_tags": ["INVOICE"]}]}

        with patch("core.utils.zugferd_extractor.ZugferdExtractor.extract_from_pdf",
                   return_value=zugferd_data):
            result = proc.run_stage_2(
                raw_ocr_pages=["Rechnung"],
                stage_1_result=stage_1_result,
                stage_1_5_result={},
                pdf_path="/tmp/test.pdf",
            )

        finance = result.get("bodies", {}).get("finance_body", {})
        assert finance.get("invoice_number") == "INV-2025-001"
        assert finance.get("due_date") == "2025-02-14"

    def test_type_tags_carried_from_stage1(self):
        """type_tags from Stage 1 must appear in semantic_data even when AI is skipped."""
        proc = _make_stage2_processor()
        zugferd_data = _make_zugferd_data()

        stage_1_result = {"type_tags": ["INVOICE"], "detected_entities": [{"type_tags": ["INVOICE"]}]}

        with patch("core.utils.zugferd_extractor.ZugferdExtractor.extract_from_pdf",
                   return_value=zugferd_data):
            result = proc.run_stage_2(
                raw_ocr_pages=["Rechnung"],
                stage_1_result=stage_1_result,
                stage_1_5_result={},
                pdf_path="/tmp/test.pdf",
            )

        assert "INVOICE" in result.get("type_tags", [])

    def test_sender_populated_from_xml_meta(self):
        """meta_header.sender must be set from ZUGFeRD meta_data."""
        proc = _make_stage2_processor()
        zugferd_data = _make_zugferd_data()

        stage_1_result = {"detected_entities": [{"type_tags": ["INVOICE"]}]}

        with patch("core.utils.zugferd_extractor.ZugferdExtractor.extract_from_pdf",
                   return_value=zugferd_data):
            result = proc.run_stage_2(
                raw_ocr_pages=["Rechnung"],
                stage_1_result=stage_1_result,
                stage_1_5_result={},
                pdf_path="/tmp/test.pdf",
            )

        sender = result.get("meta_header", {}).get("sender", {})
        assert sender.get("name") == "ACME GmbH"

    @pytest.mark.parametrize("eligible_type", ["INVOICE", "CREDIT_NOTE", "RECEIPT", "UTILITY_BILL"])
    def test_ai_skipped_for_all_eligible_types(self, eligible_type: str):
        """All four eligible document types must bypass the AI call."""
        proc = _make_stage2_processor()
        zugferd_data = _make_zugferd_data()

        stage_1_result = {"detected_entities": [{"type_tags": [eligible_type]}]}

        with patch("core.utils.zugferd_extractor.ZugferdExtractor.extract_from_pdf",
                   return_value=zugferd_data):
            proc.run_stage_2(
                raw_ocr_pages=["text"],
                stage_1_result=stage_1_result,
                stage_1_5_result={},
                pdf_path="/tmp/test.pdf",
            )

        proc.client.generate_json.assert_not_called()


# ---------------------------------------------------------------------------
# Stage 0.5 — AI still called when ZUGFeRD absent or type ineligible
# ---------------------------------------------------------------------------

class TestZugferdStage05Fallback:

    def test_ai_called_when_no_zugferd(self):
        """Without ZUGFeRD XML, client.generate_json must be called normally."""
        proc = _make_stage2_processor()
        proc.client.generate_json.return_value = {
            "meta_header": {"doc_number": "X"},
            "bodies": {"finance_body": {}},
            "repaired_text": "",
            "ai_confidence": 0.9,
        }

        stage_1_result = {"detected_entities": [{"type_tags": ["INVOICE"]}]}

        with patch("core.utils.zugferd_extractor.ZugferdExtractor.extract_from_pdf",
                   return_value=None):
            proc.run_stage_2(
                raw_ocr_pages=["Rechnung"],
                stage_1_result=stage_1_result,
                stage_1_5_result={},
                pdf_path="/tmp/test.pdf",
            )

        proc.client.generate_json.assert_called_once()

    def test_ai_called_for_ineligible_type_even_with_zugferd(self):
        """CONTRACT type must still run AI even if ZUGFeRD data is present."""
        proc = _make_stage2_processor()
        proc.client.generate_json.return_value = {
            "meta_header": {},
            "bodies": {"legal_body": {}},
            "repaired_text": "",
            "ai_confidence": 0.85,
        }

        stage_1_result = {"detected_entities": [{"type_tags": ["CONTRACT"]}]}
        zugferd_data = _make_zugferd_data()

        with patch("core.utils.zugferd_extractor.ZugferdExtractor.extract_from_pdf",
                   return_value=zugferd_data):
            proc.run_stage_2(
                raw_ocr_pages=["Vertrag"],
                stage_1_result=stage_1_result,
                stage_1_5_result={},
                pdf_path="/tmp/test.pdf",
            )

        proc.client.generate_json.assert_called_once()

    def test_no_zugferd_without_pdf_path(self):
        """Without pdf_path, ZUGFeRD detection is skipped and AI runs normally."""
        proc = _make_stage2_processor()
        proc.client.generate_json.return_value = {
            "meta_header": {},
            "bodies": {"finance_body": {}},
            "repaired_text": "",
            "ai_confidence": 0.8,
        }

        stage_1_result = {"detected_entities": [{"type_tags": ["INVOICE"]}]}

        result = proc.run_stage_2(
            raw_ocr_pages=["Rechnung"],
            stage_1_result=stage_1_result,
            stage_1_5_result={},
            pdf_path=None,
        )

        proc.client.generate_json.assert_called_once()
        assert result is not None


# ---------------------------------------------------------------------------
# SemanticExtraction model — extraction_source field
# ---------------------------------------------------------------------------

class TestSemanticExtractionSourceField:

    def test_extraction_source_field_exists(self):
        from core.models.semantic import SemanticExtraction
        se = SemanticExtraction()
        assert se.extraction_source is None

    def test_extraction_source_accepts_zugferd_native(self):
        from core.models.semantic import SemanticExtraction
        se = SemanticExtraction(extraction_source="ZUGFERD_NATIVE")
        assert se.extraction_source == "ZUGFERD_NATIVE"

    def test_extraction_source_round_trips_json(self):
        from core.models.semantic import SemanticExtraction
        se = SemanticExtraction(extraction_source="ZUGFERD_NATIVE")
        dumped = se.model_dump()
        reloaded = SemanticExtraction(**dumped)
        assert reloaded.extraction_source == "ZUGFERD_NATIVE"


# ---------------------------------------------------------------------------
# ZugferdExtractor — type_tags from document type code
# ---------------------------------------------------------------------------

class TestZugferdExtractorTypeCode:

    def _parse_xml(self, type_code: str) -> dict:
        """Build minimal CII XML with the given TypeCode and parse it."""
        from core.utils.zugferd_extractor import ZugferdExtractor
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
    xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
    xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocument>
    <ram:ID>TEST-001</ram:ID>
    <ram:TypeCode>{type_code}</ram:TypeCode>
    <ram:IssueDateTime><udt:DateTimeString>20250115</udt:DateTimeString></ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    <ram:ApplicableHeaderTradeAgreement/>
    <ram:ApplicableHeaderTradeDelivery/>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:ApplicableTradeSettlementMonetarySummation/>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>""".encode()
        return ZugferdExtractor.parse_cii_xml(xml)

    def test_type_code_380_is_invoice(self):
        result = self._parse_xml("380")
        assert result["type_tags"] == ["INVOICE"]

    def test_type_code_381_is_credit_note(self):
        result = self._parse_xml("381")
        assert result["type_tags"] == ["CREDIT_NOTE"]

    def test_type_code_383_falls_back_to_invoice(self):
        result = self._parse_xml("383")
        assert result["type_tags"] == ["INVOICE"]

    def test_unknown_type_code_defaults_to_invoice(self):
        result = self._parse_xml("999")
        assert result["type_tags"] == ["INVOICE"]

    def test_type_tags_key_always_present(self):
        result = self._parse_xml("380")
        assert "type_tags" in result
        assert isinstance(result["type_tags"], list)
        assert len(result["type_tags"]) > 0
