"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/identity_parser.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Turns a free-text signature / imprint into a structured
                IdentityProfile with one JSON prompt sent through the
                analysis engine's LLM (Settings > Identity).
------------------------------------------------------------------------------
"""

from typing import Any, List, Optional

from core.engines.fluxsense_client import FluxSenseClient
from core.logger import get_logger
from core.models.identity import IdentityProfile

logger = get_logger("identity_parser")

PROMPT_IDENTITY_PARSE = """
You are a Settings Assistant.
Extract user identity data from the provided signature/imprint text.

### TARGET JSON SCHEMA
{{
  "name": "String (Official Person Name or Main Entity Name)",
  "aliases": ["String", "String"], // Variations of the name

  "company_name": "String (Official Company Name, e.g. 'ACME GmbH')",
  "company_aliases": ["String"], // e.g. 'ACME', 'ACME Germany'

  "address_keywords": ["String", "String"], // City, Street, Zip (atomic parts)
  "vat_id": "String (or null)",
  "iban": ["String"] // List of IBANs found
}}

### RULES
- **Company:** If a company is mentioned (e.g. 'GmbH', 'Inc'), extract it specifically into `company_name`.
- **Aliases:** Generate plausible variations if not explicitly stated (e.g. if Name is "Thomas Müller", Alias could be "T. Müller").
- **Address Keywords:** Do NOT return the full address string. Return the unique parts (Streetname, Zip, City) as a list for fuzzy matching later.
- **VAT/IBAN:** Extract strictly. If not present, return `null`. **DO NOT GUESS.**
- **GROUNDING:** Only extract what is explicitly written in the signature/imprint.

### INPUT TEXT
{text}
"""


def _string_list(value: Any) -> List[str]:
    """Normalizes a JSON value into a list of non-empty strings."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if item is not None and str(item).strip()]


def _optional_string(value: Any) -> Optional[str]:
    """Normalizes a JSON value into a stripped string or None."""
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None


def profile_from_json(data: Any) -> Optional[IdentityProfile]:
    """
    Builds an IdentityProfile from the model's JSON answer.

    Args:
        data: Parsed JSON answer.

    Returns:
        The profile, or None if the answer is not an object.
    """
    if not isinstance(data, dict):
        return None
    return IdentityProfile(
        name=_optional_string(data.get("name")),
        aliases=_string_list(data.get("aliases")),
        company_name=_optional_string(data.get("company_name")),
        company_aliases=_string_list(data.get("company_aliases")),
        address_keywords=_string_list(data.get("address_keywords")),
        vat_id=_optional_string(data.get("vat_id")),
        iban=_string_list(data.get("iban")),
    )


def parse_identity_signature(text: str, client: FluxSenseClient) -> Optional[IdentityProfile]:
    """
    Extracts a structured identity profile from a signature text.

    Args:
        text: Signature / imprint text entered by the user.
        client: Engine client used for the LLM request.

    Returns:
        The profile, or None if the model gave no usable answer.

    Raises:
        FluxSenseError: If the engine cannot run free prompts or the backend failed.
    """
    answer = client.complete_json(PROMPT_IDENTITY_PARSE.format(text=text), "IDENTITY PARSE REQUEST")
    profile = profile_from_json(answer)
    if profile is None:
        logger.info("Identity parsing returned no usable JSON object")
    return profile
