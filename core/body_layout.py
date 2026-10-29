"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/body_layout.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Which semantic bodies belong to which document type (the
                FluxSense catalog layout: finance_body, statement_body,
                payslip_body, legal_body, correspondence_body, ...). Used by
                the maintenance check and when the user changes a type.
------------------------------------------------------------------------------
"""

from typing import Dict, FrozenSet, Iterable, List, Mapping, Set

_FINANCE = frozenset({"finance_body", "subscription_info"})

# Output types of the FluxSense catalog -> bodies its extraction produces.
TYPE_BODIES: Dict[str, FrozenSet[str]] = {
    **{t: _FINANCE for t in ("INVOICE", "CREDIT_NOTE", "RECEIPT", "UTILITY_BILL", "DUNNING", "ORDER",
                             "ORDER_CONFIRMATION", "QUOTE", "EXPENSE_REPORT", "TAX_ASSESSMENT")},
    "DELIVERY_NOTE": frozenset({"finance_body"}),
    "BANK_STATEMENT": frozenset({"statement_body"}),
    "PAYSLIP": frozenset({"payslip_body"}),
    **{t: frozenset({"legal_body"}) for t in ("CONTRACT", "INSURANCE_POLICY", "LEGAL_CORRESPONDENCE", "CERTIFICATE")},
    "OFFICIAL_LETTER": frozenset({"legal_body", "correspondence_body"}),
    **{t: frozenset({"correspondence_body"}) for t in ("MEDICAL_DOCUMENT", "VEHICLE_REGISTRATION", "APPLICATION",
                                                         "NOTE", "OTHER")},
}

KNOWN_BODIES: FrozenSet[str] = frozenset().union(*TYPE_BODIES.values())
# Optional companions that never make a document inconsistent on their own.
AUXILIARY_BODIES: FrozenSet[str] = frozenset({"subscription_info"})


def expected_bodies(type_tags: Iterable[str]) -> Set[str]:
    """
    Bodies that the document types in type_tags may carry.

    Args:
        type_tags: Type tags (direction / CTX_ tags and unknown tags are ignored).

    Returns:
        Union of the expected bodies; empty if no tag has a known layout.
    """
    expected: Set[str] = set()
    for tag in type_tags or []:
        expected |= TYPE_BODIES.get(str(tag).upper(), frozenset())
    return expected


def unexpected_bodies(type_tags: Iterable[str], bodies: Mapping[str, object]) -> List[str]:
    """
    Non-empty known bodies that none of the document's types explains.

    Missing bodies are not reported: an engine leaves a body out when the
    document has nothing for it (empty fields are not errors).

    Args:
        type_tags: The document's type tags.
        bodies: semantic_data.bodies.

    Returns:
        Sorted body keys; empty if the layout is consistent or no type is known.
    """
    expected = expected_bodies(type_tags)
    if not expected:
        return []
    return sorted(key for key, value in (bodies or {}).items()
                  if key in KNOWN_BODIES and key not in AUXILIARY_BODIES and key not in expected and value)
