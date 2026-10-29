"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_body_layout.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    FluxSense body layout, the 'mismatched semantic data'
                maintenance check and the review_count filter.
------------------------------------------------------------------------------
"""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from core.body_layout import expected_bodies, unexpected_bodies
from core.database import DatabaseManager
from core.engines.fluxsense_adapter import adapt_result, flatten_source_mapping
from core.models.semantic import SemanticExtraction
from core.models.virtual import SourceReference, VirtualDocument
from core.query_builder import QueryBuilder
from core.repositories import LogicalRepository

FIXTURE = Path(__file__).parent.parent / "resources" / "fluxsense" / "synthetic_stack_result.json"


def test_expected_bodies_follow_the_fluxsense_catalog() -> None:
    """Each output type maps onto the bodies FluxSense produces for it."""
    assert expected_bodies(["INVOICE", "INBOUND", "CTX_PRIVATE"]) == {"finance_body", "subscription_info"}
    assert expected_bodies(["BANK_STATEMENT"]) == {"statement_body"}
    assert expected_bodies(["OFFICIAL_LETTER"]) == {"legal_body", "correspondence_body"}
    assert expected_bodies(["PAYSLIP"]) == {"payslip_body"}
    assert expected_bodies(["CUSTOM_TAG"]) == set()


@pytest.mark.parametrize("tags, bodies, expected", [
    (["BANK_STATEMENT"], {"statement_body": {"iban": "X"}}, []),
    (["INVOICE"], {"finance_body": {"invoice_number": "1"}, "subscription_info": {"is_recurring": True}}, []),
    (["APPLICATION"], {"correspondence_body": {"subject": "x"}}, []),
    (["INVOICE"], {}, []),  # missing bodies are not errors
    (["INVOICE"], {"statement_body": {"iban": "X"}}, ["statement_body"]),
    (["BANK_STATEMENT"], {"finance_body": {"invoice_number": "1"}, "statement_body": {}}, ["finance_body"]),
    (["CUSTOM_TAG"], {"statement_body": {"iban": "X"}}, []),
    (["INVOICE"], {"other_body": {"x": 1}}, []),
])
def test_unexpected_bodies(tags: list, bodies: Dict[str, Any], expected: list) -> None:
    """Only non-empty known bodies that no type explains are reported."""
    assert unexpected_bodies(tags, bodies) == expected


@pytest.fixture
def db_with_fluxsense_docs() -> DatabaseManager:
    """The synthetic stack's three documents plus one inconsistent document."""
    db = DatabaseManager(":memory:")
    db.init_db()
    repo = LogicalRepository(db)
    result = json.loads(FIXTURE.read_text(encoding="utf-8"))
    refs = flatten_source_mapping([SourceReference(file_uuid="f", pages=[1, 2, 3, 4, 5])])
    for index, entity in enumerate(adapt_result(result, refs)):
        repo.save(VirtualDocument(uuid=f"doc-{index}", type_tags=entity.type_tags, semantic_data=entity.semantic,
                                  source_mapping=entity.source_mapping, status="PROCESSED"))
    wrong = SemanticExtraction(bodies={"statement_body": {"iban": "DE89370400440532013000"}})
    repo.save(VirtualDocument(uuid="wrong", type_tags=["INVOICE"], semantic_data=wrong, status="PROCESSED"))
    return db


def test_maintenance_check_understands_the_fluxsense_layout(db_with_fluxsense_docs: DatabaseManager) -> None:
    """FluxSense documents (statement_body, correspondence_body) are not flagged; a wrong body is."""
    assert [d.uuid for d in db_with_fluxsense_docs.get_documents_mismatched_semantic_data()] == ["wrong"]


def test_review_count_filter(db_with_fluxsense_docs: DatabaseManager) -> None:
    """The 'Fields to Review' query field finds documents with open review items."""
    where, params = QueryBuilder().build_where({"field": "review_count", "op": "gt", "value": 0})
    rows = db_with_fluxsense_docs.connection.execute(
        f"SELECT uuid FROM virtual_documents WHERE {where} ORDER BY uuid", params).fetchall()
    assert [r[0] for r in rows] == ["doc-0", "doc-2"]  # invoice (2 flagged) and letter (1); the statement has none
    doc = db_with_fluxsense_docs.get_document_by_uuid("doc-0")
    assert doc.review_count == 2
    assert db_with_fluxsense_docs.get_document_by_uuid("wrong").review_count is None
