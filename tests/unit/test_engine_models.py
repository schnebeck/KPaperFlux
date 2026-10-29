"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_engine_models.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Tests for the engine review metadata (semantic_data.engine)
                and the typed statement body.
------------------------------------------------------------------------------
"""

from decimal import Decimal

from core.models.semantic import EngineInfo, FieldReviewState, SemanticExtraction, StatementBody


def test_engine_info_field_lookup() -> None:
    """field_state() and fields_needing_review() expose per-field review state."""
    info = EngineInfo(name="fluxsense", fields=[
        FieldReviewState(path="meta_header.doc_date", value="2026-01-01", auto_accepted=True, provenance="label"),
        FieldReviewState(path="bodies.finance_body.due_date", value="2026-02-01", auto_accepted=False,
                         review_reasons=["model reading only"]),
        FieldReviewState(path="meta_header.sender.city", value=None, auto_accepted=None),
    ])
    assert info.field_state("meta_header.doc_date").provenance == "label"
    assert info.field_state("does.not.exist") is None
    assert [f.path for f in info.fields_needing_review()] == ["bodies.finance_body.due_date"]


def test_semantic_extraction_keeps_engine_block() -> None:
    """The engine block is a real model field and survives a dump/validate round trip."""
    sem = SemanticExtraction(engine={"name": "fluxsense", "version": "0.1.0", "fields": [{"path": "meta_header.doc_number", "value": "X"}]})
    restored = SemanticExtraction.model_validate(sem.model_dump(mode="json"))
    assert restored.engine.version == "0.1.0"
    assert restored.engine.fields[0].value == "X"


def test_malformed_engine_block_is_dropped_not_fatal() -> None:
    """Corrupt engine metadata must not make the whole semantic data unreadable."""
    assert SemanticExtraction.model_validate({"engine": {"version": "no name"}}).engine is None
    assert SemanticExtraction.model_validate({"engine": "fluxsense"}).engine is None


def test_statement_body_is_parsed_and_tolerant() -> None:
    """statement_body becomes a typed model; unknown keys are kept, IBAN normalized."""
    sem = SemanticExtraction(bodies={"statement_body": {
        "iban": "de02 1203 0000 0000 2020 51", "closing_balance": "10.50", "new_engine_key": 1,
        "transactions": [{"amount": "-1.20", "booking_date": "2026-01-02", "extra": "kept"}]}})
    body = sem.bodies["statement_body"]
    assert isinstance(body, StatementBody)
    assert body.iban == "DE02120300000000202051"
    assert body.closing_balance == Decimal("10.50")
    assert body.transactions[0].amount == Decimal("-1.20")
    assert body.model_dump()["new_engine_key"] == 1
    assert body.transactions[0].model_dump()["extra"] == "kept"
