"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_order_collection_linker.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Order collections link documents of one order chain, not all
                documents of a supplier.
------------------------------------------------------------------------------
"""
from core.models.semantic import DocumentReference, FinanceBody, MetaHeader, SemanticExtraction
from core.models.virtual import VirtualDocument
from core.plugins.base import ApiContext
from plugins.order_collection_linker.linker import OrderCollectionLinker


def _doc(uuid: str, refs=(), **finance) -> VirtualDocument:
    return VirtualDocument(uuid=uuid, semantic_data=SemanticExtraction(
        meta_header=MetaHeader(references=[DocumentReference(ref_type=t, ref_value=v) for t, v in refs]),
        bodies={"finance_body": FinanceBody(**finance)}))


def _clusters(docs) -> list:
    return sorted(sorted(c) for c in OrderCollectionLinker(ApiContext()).find_process_clusters(docs))


def test_order_and_invoice_with_the_same_order_number_are_linked():
    docs = [_doc("order", order_number="PO-2026-0815"),
            _doc("invoice", invoice_number="RE-4711", order_number="PO-2026-0815")]
    assert _clusters(docs) == [["invoice", "order"]]


def test_shared_customer_number_does_not_link_unrelated_orders():
    docs = [_doc("jan", invoice_number="RE-1001", customer_id="K-20077",
                 refs=[("CUSTOMER_ID", "K-20077")]),
            _doc("feb", invoice_number="RE-1002", customer_id="K-20077",
                 refs=[("CUSTOMER_ID", "K-20077")])]
    assert _clusters(docs) == []


def test_chains_are_linked_transitively():
    docs = [_doc("offer", refs=[("OFFER_ID", "AN-2026-7")]),
            _doc("order", order_number="PO-77", refs=[("OFFER_ID", "AN-2026-7")]),
            _doc("invoice", order_number="PO-77")]
    assert _clusters(docs) == [["invoice", "offer", "order"]]


def test_short_or_generic_tokens_and_missing_data_are_ignored():
    docs = [_doc("a", order_number="ABC"), _doc("b", order_number="ABC"),
            VirtualDocument(uuid="no-data"), VirtualDocument(uuid="no-data-2")]
    assert _clusters(docs) == []
