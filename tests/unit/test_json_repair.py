"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_json_repair.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Unit tests for the shared tiered JSON repair module.
------------------------------------------------------------------------------
"""

import pytest

from core.ai.json_repair import parse_json_response


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('[{"a": 1}, {"b": 2}]', [{"a": 1}, {"b": 2}]),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('Sure! Here is the JSON:\n{"a": {"b": 2}}\nHope this helps.', {"a": {"b": 2}}),
        ('{"a": 1} trailing {"garbage": true}', {"a": 1}),
        ('{"a": [1, 2,], "b": 3,}', {"a": [1, 2], "b": 3}),
        ('{"a": {"x": 1}\n"b": 2}', {"a": {"x": 1}, "b": 2}),
        ('{"items": [{"x": 1}, {"x": 2', {"items": [{"x": 1}, {"x": 2}]}),
        ('{"text": "unterminated', {"text": "unterminated"}),
        ('{"a": "brace } in string", "b": 1}', {"a": "brace } in string", "b": 1}),
        ('{"a": 1, "b"', {"a": 1, "b": None}),
        ('{"a": "x"}\x00', {"a": "x"}),
    ],
)
def test_parse_and_repair(raw: str, expected: object) -> None:
    result, error = parse_json_response(raw)
    assert error is None
    assert result == expected


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty_response(raw: object) -> None:
    result, error = parse_json_response(raw)  # type: ignore[arg-type]
    assert result is None
    assert error == "Empty response"


def test_no_json_object() -> None:
    result, error = parse_json_response("I cannot help with that.")
    assert result is None
    assert "missing" in error


def test_unrepairable() -> None:
    result, error = parse_json_response("{not json at all")
    assert result is None
    assert error == "JSON Syntax Error after repair attempts"
