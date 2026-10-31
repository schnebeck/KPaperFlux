"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_semantic_edit.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Section resolution and dotted-path writes of the semantic table.
------------------------------------------------------------------------------
"""
from core.semantic_edit import section_root, set_path


def test_meta_and_custom_sections():
    sd = {"meta_header": {"doc_number": "1"}}
    assert section_root(sd, "Meta") is sd["meta_header"]
    assert section_root(sd, "Custom") == {} and "custom_fields" in sd


def test_body_sections_prefer_existing_containers():
    sd = {"bodies": {"finance_body": {"currency": "EUR"}, "legal": {"x": 1}}}
    assert section_root(sd, "Finance") is sd["bodies"]["finance_body"]
    assert section_root(sd, "Legal") is sd["bodies"]["legal"]


def test_missing_body_is_created():
    sd = {"bodies": None}
    root = section_root(sd, "Statement")
    assert sd["bodies"] == {"statement_body": {}} and root is sd["bodies"]["statement_body"]


def test_set_path_creates_lists_and_dicts():
    root = {}
    set_path(root, "line_items.1.price", "9.99")
    assert root == {"line_items": [{}, {"price": "9.99"}]}
    set_path(root, "monetary_summation.grand_total_amount", "119.00")
    assert root["monetary_summation"] == {"grand_total_amount": "119.00"}


def test_set_path_into_existing_list_entry():
    root = {"tags": ["a", "b"]}
    set_path(root, "tags.1", "c")
    set_path(root, "tags.3", "e")
    assert root["tags"] == ["a", "c", None, "e"]
