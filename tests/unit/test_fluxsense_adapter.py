"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_fluxsense_adapter.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Contract and unit tests for the FluxSense result adapter. The
                fixture is a synthetic AnalysisResult (invented parties, test
                IBANs) generated through FluxSense's own result models, so its
                shape matches real engine output key for key.
------------------------------------------------------------------------------
"""

import copy
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import pytest

from core.engines.fluxsense_adapter import (
    ENGINE_NAME,
    FluxSenseResultError,
    PageRef,
    adapt_result,
    build_type_tags,
    engine_error_info,
    flatten_source_mapping,
    is_whole_file,
    map_pages_to_source,
    resolve_field_path,
)
from core.models.semantic import (
    FinanceBody,
    LegalBody,
    SemanticExtraction,
    StatementBody,
    VisualAuditResult,
)
from core.models.virtual import SourceReference, VirtualDocument
from core.repositories.logical_repo import EnhancedJSONEncoder

FIXTURE = Path(__file__).parent.parent / "resources" / "fluxsense" / "synthetic_stack_result.json"

# Values KPaperFlux intentionally does not keep in the semantic body (preserved elsewhere).
_RELOCATED_LEAVES = {"source_page"}


@pytest.fixture
def result() -> Dict[str, Any]:
    """The synthetic 5-page stack: invoice (1-2), bank statement (3-4), letter (5)."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def page_refs() -> List[PageRef]:
    """Whole 5-page physical file analyzed as is."""
    return flatten_source_mapping([SourceReference(file_uuid="file-a", pages=[1, 2, 3, 4, 5])])


def _leaves(node: Any, prefix: str = "") -> Iterator[Tuple[str, Any]]:
    """Yields (dotted path, value) for every scalar leaf of a JSON structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, f"{prefix}{key}.")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, f"{prefix}{index}.")
    else:
        yield prefix.rstrip("."), node


def _same(expected: Any, actual: Any) -> bool:
    """Compares JSON values with KPaperFlux model values (Decimal vs. numeric string)."""
    if isinstance(actual, Decimal) or isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except InvalidOperation:
            return False
    return expected == actual


# ------------------------------------------------------------------ contract

def test_contract_three_logical_documents_with_page_mapping(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """Each logical document becomes one entity with its own source mapping."""
    entities = adapt_result(result, page_refs)
    assert [e.pages for e in entities] == [[1, 2], [3, 4], [5]]
    assert [[(r.file_uuid, r.pages) for r in e.source_mapping] for e in entities] == [
        [("file-a", [1, 2])], [("file-a", [3, 4])], [("file-a", [5])]]
    assert not any(e.failed for e in entities)


def test_contract_invoice_core_fields(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """Sender, recipient, date, number, amounts, IBAN, due date and line items survive typed."""
    invoice = adapt_result(result, page_refs)[0]
    sem = invoice.semantic
    fb = sem.bodies["finance_body"]
    assert isinstance(fb, FinanceBody)
    assert sem.meta_header.sender.company == "Muster Elektro GmbH"
    assert sem.meta_header.sender.zip_code == "10115"
    assert sem.meta_header.recipient.name == "Erika Mustermann"
    assert sem.meta_header.doc_date == "2026-03-14"
    assert sem.meta_header.doc_number == "RE-2026-0042"
    assert fb.due_date == "2026-03-28"
    assert fb.monetary_summation.grand_total_amount == Decimal("357.00")
    assert fb.monetary_summation.tax_total_amount == Decimal("57.00")
    assert fb.monetary_summation.tax_basis_total_amount == Decimal("300.00")
    assert fb.payment_accounts[0].iban == "DE89370400440532013000"
    assert [li.total_price for li in fb.line_items] == [Decimal("100.00"), Decimal("200.00")]
    assert fb.tax_breakdown[0].tax_rate == Decimal("19")
    assert isinstance(sem.visual_audit, VisualAuditResult)
    assert sem.visual_audit.meta_mode == "NONE"

    doc = VirtualDocument(semantic_data=sem, type_tags=invoice.type_tags)
    assert doc.sender_name == "Muster Elektro GmbH"
    assert doc.recipient_name == "Erika Mustermann"
    assert doc.doc_number == "RE-2026-0042"
    assert doc.total_gross == Decimal("357.00")
    assert doc.iban == "DE89370400440532013000"
    assert doc.due_date == "2026-03-28"


def test_contract_statement_period_balances_transactions(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """Statement period, balances and bookings load into the typed StatementBody."""
    statement = adapt_result(result, page_refs)[1]
    body = statement.semantic.bodies["statement_body"]
    assert isinstance(body, StatementBody)
    assert (body.period_start, body.period_end) == ("2026-03-01", "2026-03-31")
    assert body.opening_balance == Decimal("1250.00")
    assert body.closing_balance == Decimal("943.00")
    assert body.iban == "DE02120300000000202051"
    assert [t.amount for t in body.transactions] == [Decimal("2100.00"), Decimal("-2050.00"), Decimal("-357.00")]
    assert body.transactions[2].description == "Muster Elektro GmbH RE-2026-0042"
    assert body.transactions[0].source_page == 1


def test_contract_no_loss_of_any_field_value(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """Every scalar FluxSense field value is reachable at the same path in KPaperFlux's model."""
    for entity, doc in zip(adapt_result(result, page_refs), result["logical_documents"]):
        dumped = entity.semantic.model_dump()
        for section in ("meta_header", "bodies"):
            for path, expected in _leaves(doc["fields"][section], f"{section}."):
                if path.split(".")[-1] in _RELOCATED_LEAVES and "line_items" in path:
                    continue
                assert _same(expected, resolve_field_path(dumped, path)), path


def test_contract_untyped_bodies_kept_verbatim(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """Bodies without a KPaperFlux model (correspondence_body) stay plain dicts."""
    letter = adapt_result(result, page_refs)[2]
    expected = result["logical_documents"][2]["fields"]["bodies"]["correspondence_body"]
    assert letter.semantic.bodies["correspondence_body"] == expected
    assert letter.semantic.engine.warnings == []


def test_contract_line_item_source_pages_preserved_in_engine_tables(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """The per-row page (no LineItem field) is kept in the engine table metadata."""
    tables = adapt_result(result, page_refs)[0].semantic.engine.tables
    assert tables[0]["path"] == "bodies.finance_body.line_items"
    assert tables[0]["row_pages"] == [1, 2]
    assert "rows" not in tables[0]


def test_contract_type_tags_and_confidence(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """type/direction/tenant become type_tags; ai_confidence comes from the trust score."""
    invoice, statement, letter = adapt_result(result, page_refs)
    assert invoice.type_tags == ["INVOICE", "INBOUND", "CTX_PRIVATE"]
    assert statement.type_tags == ["BANK_STATEMENT", "INBOUND", "CTX_PRIVATE"]
    assert letter.type_tags == ["OFFICIAL_LETTER", "INBOUND"]
    assert invoice.semantic.type_tags == ["INVOICE"]
    assert invoice.ai_confidence == pytest.approx(0.88)
    assert invoice.semantic.ai_confidence == pytest.approx(0.88)
    assert invoice.semantic.direction == "INBOUND"
    assert letter.semantic.tenant_context == "UNKNOWN"


def test_contract_engine_review_state(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """Engine name/versions and per-field review state are stored for the MetadataEditor."""
    invoice, statement, _ = adapt_result(result, page_refs)
    engine = invoice.semantic.engine
    assert (engine.name, engine.version, engine.prompt_version) == (ENGINE_NAME, "0.1.0", "test-prompts-1")
    assert engine.subtype == "INVOICE"
    assert engine.model_confidence == pytest.approx(0.93)
    assert engine.analyzed_pages == [1, 2]
    assert len(engine.fields) == 10
    assert {f.path for f in engine.fields_needing_review()} == {
        "meta_header.sender.phone", "bodies.finance_body.due_date"}

    phone = engine.field_state("meta_header.sender.phone")
    assert phone.value is None and phone.original_value == "+49 30 7654321"
    assert phone.action == "nulled"
    assert "failing check: grounding.ungrounded" in phone.review_reasons

    company = engine.field_state("meta_header.sender.company")
    assert company.provenance == "geometry" and company.auto_accepted is True
    assert company.bbox == [60.0, 40.0, 380.0, 70.0]
    assert engine.field_state("bodies.finance_body.due_date").page == 2
    assert engine.plausibility["status"] == "WARN"
    assert engine.trust["score"] == pytest.approx(0.88)

    # Pages are document-local: the statement's page 3 of the stack is its page 1.
    assert statement.semantic.engine.field_state("bodies.statement_body.iban").page == 1


def test_contract_kept_evidence_paths_resolve_to_field_values(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """Evidence paths address the semantic data directly (basis for per-field highlighting)."""
    for entity in adapt_result(result, page_refs):
        dumped = entity.semantic.model_dump()
        for state in entity.semantic.engine.fields:
            if state.action == "kept":
                assert _same(state.value, resolve_field_path(dumped, state.path)), state.path


def test_contract_round_trip_through_repository_json(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """semantic_data survives the DB JSON encoding and re-hydration with engine state intact."""
    invoice, statement, _ = adapt_result(result, page_refs)
    for entity in (invoice, statement):
        raw = json.loads(json.dumps(entity.semantic, cls=EnhancedJSONEncoder))
        restored = SemanticExtraction.model_validate(raw)
        assert restored.engine is not None
        assert restored.engine.model_dump() == entity.semantic.engine.model_dump()
        assert type(restored.bodies[next(iter(restored.bodies))]) in (FinanceBody, StatementBody)
    restored = SemanticExtraction.model_validate(json.loads(json.dumps(invoice.semantic, cls=EnhancedJSONEncoder)))
    assert restored.bodies["finance_body"].monetary_summation.grand_total_amount == Decimal("357.0")


# ------------------------------------------------------------------ pages

def test_map_pages_groups_by_file_and_rotation() -> None:
    """A stitched input maps back to the original files, pages and rotations."""
    refs = flatten_source_mapping([
        SourceReference(file_uuid="a", pages=[2, 3], rotation=0),
        SourceReference(file_uuid="b", pages=[1], rotation=90),
        SourceReference(file_uuid="a", pages=[7], rotation=0),
    ])
    assert [(r.file_uuid, r.page, r.rotation) for r in refs] == [("a", 2, 0), ("a", 3, 0), ("b", 1, 90), ("a", 7, 0)]
    mapping = map_pages_to_source([1, 2, 3, 4], refs)
    assert [(m.file_uuid, m.pages, m.rotation) for m in mapping] == [("a", [2, 3], 0), ("b", [1], 90), ("a", [7], 0)]
    assert [(m.file_uuid, m.pages) for m in map_pages_to_source([4, 9], refs)] == [("a", [7])]
    assert map_pages_to_source([], refs) == []


def test_is_whole_file() -> None:
    """Only a complete, unrotated single file can be analyzed in place."""
    assert is_whole_file(flatten_source_mapping([SourceReference(file_uuid="a", pages=[1, 2])]), 2)
    assert not is_whole_file(flatten_source_mapping([SourceReference(file_uuid="a", pages=[1, 2])]), 3)
    assert not is_whole_file(flatten_source_mapping([SourceReference(file_uuid="a", pages=[2, 1])]), 2)
    assert not is_whole_file(flatten_source_mapping([SourceReference(file_uuid="a", pages=[1, 2], rotation=180)]), 2)
    assert not is_whole_file([], 0)


def test_stitched_input_maps_entities_to_physical_pages(result: Dict[str, Any]) -> None:
    """Entity pages refer to the analyzed (stitched) PDF and are translated back."""
    refs = flatten_source_mapping([SourceReference(file_uuid="x", pages=[10, 11, 12, 13, 14])])
    entities = adapt_result(result, refs)
    assert [e.source_mapping[0].pages for e in entities] == [[10, 11], [12, 13], [14]]


# ------------------------------------------------------------------ result handling

def test_keep_single_suppresses_split(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """Protected documents stay one entity covering all pages."""
    entities = adapt_result(result, page_refs, keep_single=True)
    assert len(entities) == 1
    assert entities[0].source_mapping[0].pages == [1, 2, 3, 4, 5]
    assert entities[0].type_tags[0] == "INVOICE"
    assert "suppressed" in entities[0].semantic.engine.warnings[0]


def test_error_status_raises(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """An engine-level ERROR is not adapted (document stays retryable)."""
    result["status"] = "ERROR"
    with pytest.raises(FluxSenseResultError):
        adapt_result(result, page_refs)
    with pytest.raises(FluxSenseResultError):
        adapt_result({"status": "OK"}, page_refs)


def test_no_logical_documents_returns_empty(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """FluxSense found nothing: no entities."""
    result["logical_documents"] = []
    assert adapt_result(result, page_refs) == []


def test_failed_document_is_flagged(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """A logical document with errors and no fields is marked failed with zero confidence."""
    result["status"] = "PARTIAL"
    result["logical_documents"][2]["fields"] = {}
    result["logical_documents"][2]["errors"] = ["Stage 2 extraction failed"]
    letter = adapt_result(result, page_refs)[2]
    assert letter.failed is True
    assert letter.ai_confidence == 0.0
    assert letter.errors == ["Stage 2 extraction failed"]
    assert "Stage 2 extraction failed" in letter.semantic.engine.errors
    assert letter.semantic.engine.status == "PARTIAL"


def test_invalid_meta_header_is_kept_unvalidated(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """A section that fails validation is preserved verbatim instead of dropping the document."""
    result["logical_documents"][0]["fields"]["meta_header"]["unexpected_key"] = "x"
    invoice = adapt_result(result, page_refs)[0]
    engine = invoice.semantic.engine
    assert engine.unvalidated["meta_header"]["doc_number"] == "RE-2026-0042"
    assert any("meta_header failed validation" in w for w in engine.warnings)
    assert isinstance(invoice.semantic.bodies["finance_body"], FinanceBody)
    assert isinstance(invoice.semantic.visual_audit, VisualAuditResult)


def test_untypable_finance_body_is_reported(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """A finance body that does not match the model stays a dict and is reported."""
    bad = copy.deepcopy(result)
    bad["logical_documents"][0]["fields"]["bodies"]["finance_body"]["monetary_summation"]["grand_total_amount"] = "n/a"
    invoice = adapt_result(bad, page_refs)[0]
    assert isinstance(invoice.semantic.bodies["finance_body"], dict)
    assert any("bodies.finance_body kept as untyped dict" in w for w in invoice.semantic.engine.warnings)


def test_legal_body_is_typed() -> None:
    """legal_body maps onto LegalBody."""
    doc = {"type": "CONTRACT", "type_tags": ["CONTRACT"], "pages": [1], "direction": "INBOUND", "tenant_context": "PRIVATE",
           "fields": {"meta_header": {}, "bodies": {"legal_body": {"contract_id": "V-1", "notice_period": {"value": 3, "unit": "MONTHS"}}}},
           "trust": {"score": 0.5}, "evidence": [], "errors": []}
    result = {"status": "OK", "logical_documents": [doc]}
    entity = adapt_result(result, [PageRef("f", 1)])[0]
    body = entity.semantic.bodies["legal_body"]
    assert isinstance(body, LegalBody)
    assert body.notice_period.value == 3


@pytest.mark.parametrize("primary, tags, direction, tenant, expected", [
    ("INVOICE", ["INVOICE", "UTILITY_BILL"], "INBOUND", "PRIVATE", ["INVOICE", "UTILITY_BILL", "INBOUND", "CTX_PRIVATE"]),
    ("BANK_STATEMENT", ["INVOICE"], "UNKNOWN", "UNKNOWN", ["BANK_STATEMENT", "INVOICE"]),
    (None, [], None, None, ["OTHER"]),
    ("QUOTE", ["QUOTE"], "OUTBOUND", "BUSINESS", ["QUOTE", "OUTBOUND", "CTX_BUSINESS"]),
])
def test_build_type_tags(primary: Any, tags: List[str], direction: Any, tenant: Any, expected: List[str]) -> None:
    """Type tags: primary first, de-duplicated, direction and tenant unless unknown."""
    assert build_type_tags(primary, tags, direction, tenant) == expected


def test_error_status_names_the_low_level_cause(result: Dict[str, Any], page_refs: List[PageRef]) -> None:
    """Regression (e2e): an unreachable backend must be visible in the stored error, not just 'status ERROR'."""
    result["status"] = "ERROR"
    result["ai_calls"] = [
        {"label": "Stage 1.1 (Classification)", "model": "m", "ok": False, "error": "Backend unreachable: [Errno 111] refused"},
        {"label": "Stage 2 (OTHER)", "model": "m", "ok": False, "error": "Backend unreachable: [Errno 111] refused"},
        {"label": "ok call", "model": "m", "ok": True, "error": None},
    ]
    result["text_layer"]["warnings"] = ["ovisocr3 returned no layout for 2 pages"]
    with pytest.raises(FluxSenseResultError, match="Backend unreachable"):
        adapt_result(result, page_refs)
    info = engine_error_info("FluxSense reported status ERROR: Backend unreachable: [Errno 111] refused", result)
    assert info.errors == ["FluxSense reported status ERROR: Backend unreachable: [Errno 111] refused",
                           "Backend unreachable: [Errno 111] refused", "ovisocr3 returned no layout for 2 pages"]


def test_engine_error_info_collects_errors() -> None:
    """A failed run records engine and document errors."""
    info = engine_error_info("backend unreachable", {"fluxsense_version": "0.1.0", "errors": ["e1"],
                                                     "logical_documents": [{"errors": ["e2"]}]})
    assert info.status == "ERROR"
    assert info.errors == ["backend unreachable", "e1", "e2"]
    assert info.version == "0.1.0"


def test_resolve_field_path() -> None:
    """Dotted paths with list indices resolve on dicts and models."""
    data = {"meta_header": {"references": [{"ref_value": "A"}, {"ref_value": "B"}]}}
    assert resolve_field_path(data, "meta_header.references.1.ref_value") == "B"
    assert resolve_field_path(data, "meta_header.references.5.ref_value") is None
    assert resolve_field_path(data, "meta_header.missing.x") is None
    sem = SemanticExtraction(meta_header={"doc_number": "N-1"})
    assert resolve_field_path(sem, "meta_header.doc_number") == "N-1"
