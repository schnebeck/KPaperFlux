"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_identity_parser.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Tests for the signature -> IdentityProfile helper (engine mocked).
------------------------------------------------------------------------------
"""

from unittest.mock import MagicMock

import pytest

from core.engines.fluxsense_client import FluxSenseError
from core.identity_parser import parse_identity_signature, profile_from_json


def test_parse_identity_signature_sends_prompt_and_builds_profile() -> None:
    """The signature text is embedded in the prompt; the answer becomes a profile."""
    client = MagicMock()
    client.complete_json.return_value = {
        "name": "Erika Mustermann", "aliases": ["E. Mustermann"], "company_name": None,
        "address_keywords": ["Heidestraße", "51147", "Köln"], "vat_id": None, "iban": "DE89370400440532013000"}
    profile = parse_identity_signature("Erika Mustermann\nHeidestraße 17\n51147 Köln", client)
    prompt, label = client.complete_json.call_args.args
    assert "Heidestraße 17" in prompt and label == "IDENTITY PARSE REQUEST"
    assert profile.name == "Erika Mustermann"
    assert profile.iban == ["DE89370400440532013000"]
    assert profile.company_name is None


def test_profile_from_json_rejects_non_objects() -> None:
    """Lists, strings and None are no profile."""
    assert profile_from_json(None) is None
    assert profile_from_json(["x"]) is None
    assert profile_from_json({"aliases": "single", "vat_id": {"bad": 1}}).aliases == ["single"]


def test_engine_errors_propagate() -> None:
    """Engine errors reach the caller (shown in the settings dialog)."""
    client = MagicMock()
    client.complete_json.side_effect = FluxSenseError("REST mode")
    with pytest.raises(FluxSenseError):
        parse_identity_signature("text", client)
