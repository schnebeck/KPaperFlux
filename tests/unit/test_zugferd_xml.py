"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_zugferd_xml.py
Version:        1.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for the ZUGFeRD XML type-code mapping and the
                extraction_source field of the semantic model.
------------------------------------------------------------------------------
"""



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
