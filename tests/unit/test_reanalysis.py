"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_reanalysis.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    carry_over_user_state keeps workflow progress and confirmed
                values of the previous extraction.
------------------------------------------------------------------------------
"""
from core.models.semantic import (EngineInfo, FieldReviewState, FinanceBody, MetaHeader, SemanticExtraction,
                                  WorkflowInfo)
from core.reanalysis import carry_over_user_state, confirmed_paths


def _state(path: str, confirmed: bool) -> FieldReviewState:
    return FieldReviewState(path=path, auto_accepted=False, confirmed_by_user=confirmed,
                            confirmed_at="2026-10-01T10:00:00" if confirmed else None)


def test_without_previous_data_the_fresh_result_is_returned():
    fresh = SemanticExtraction(bodies={"finance_body": FinanceBody(invoice_number="NEW")})
    assert carry_over_user_state(None, fresh) is fresh


def test_unconfirmed_values_are_replaced_confirmed_ones_kept():
    previous = SemanticExtraction(
        bodies={"finance_body": FinanceBody(invoice_number="USER-1", order_number="OLD-ORDER")},
        engine=EngineInfo(name="fluxsense", fields=[_state("bodies.finance_body.invoice_number", True),
                                                    _state("bodies.finance_body.order_number", False)]))
    fresh = SemanticExtraction(
        bodies={"finance_body": FinanceBody(invoice_number="ENGINE-1", order_number="NEW-ORDER")},
        engine=EngineInfo(name="fluxsense", fields=[_state("bodies.finance_body.invoice_number", False)]))

    merged = carry_over_user_state(previous, fresh)

    assert merged.bodies["finance_body"].invoice_number == "USER-1"
    assert merged.bodies["finance_body"].order_number == "NEW-ORDER"
    assert confirmed_paths(merged) == ["bodies.finance_body.invoice_number"]
    assert merged.engine.field_state("bodies.finance_body.invoice_number").value == "USER-1"


def test_confirmed_list_entry_and_missing_state_are_carried_over():
    previous = SemanticExtraction(
        meta_header=MetaHeader(references=[{"ref_type": "ORDER", "ref_value": "A-77"}]),
        engine=EngineInfo(name="fluxsense", fields=[_state("meta_header.references.0.ref_value", True)]))
    fresh = SemanticExtraction(engine=EngineInfo(name="fluxsense"))

    merged = carry_over_user_state(previous, fresh)

    assert merged.meta_header.references[0].ref_value == "A-77"
    assert confirmed_paths(merged) == ["meta_header.references.0.ref_value"]


def test_workflows_are_kept_and_new_ones_added():
    previous = SemanticExtraction(workflows={"rule-a": WorkflowInfo(rule_id="rule-a", current_step="PAID")})
    fresh = SemanticExtraction(workflows={"rule-a": WorkflowInfo(rule_id="rule-a", current_step="NEW"),
                                          "rule-b": WorkflowInfo(rule_id="rule-b", current_step="NEW")})

    merged = carry_over_user_state(previous, fresh)

    assert merged.workflows["rule-a"].current_step == "PAID"
    assert merged.workflows["rule-b"].current_step == "NEW"
