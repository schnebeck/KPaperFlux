"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/validators.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Fuzzy validation logic for identity verification and AI 
                structural integrity. Provides heuristic checks for tenant 
                contexts (PRIVATE/BUSINESS) based on OCR text analysis.
------------------------------------------------------------------------------
"""

import difflib
from typing import Any, Dict, List, Optional

from core.models.identity import IdentityProfile


def check_identity_fuzzy(ocr_text: str, identity_profile: Optional[IdentityProfile]) -> bool:
    """
    Validates if an identity profile is likely present in the provided OCR text.
    Uses hierarchical heuristics:
    1. ZIP code match (High confidence).
    2. Fuzzy text word matching via difflib.
    3. Prefix search for truncated company/person names.

    Args:
        ocr_text: The source text from OCR analysis.
        identity_profile: The profile to search for.

    Returns:
        True if the identity is found with sufficient confidence.
    """
    if not identity_profile:
        return False

    text_lower = ocr_text.lower()

    # 1. ZIP/PLZ Check
    # Very reliable as numbers are often preserved better than complex text in OCR.
    for keyword in identity_profile.address_keywords:
        # Standard German 5-digit ZIP check
        if keyword.isdigit() and len(keyword) == 5:
            if keyword in text_lower:
                return True

    # 2. Heuristic Text Search
    search_terms: List[str] = []
    if identity_profile.company_name:
        search_terms.append(identity_profile.company_name)

    # Use textual keywords (exclude pure numbers which are handled by ZIP check)
    search_terms += [k for k in identity_profile.address_keywords if not k.isdigit()]

    if identity_profile.name:
        search_terms.append(identity_profile.name)

    search_terms += identity_profile.aliases

    threshold = 0.6  # 60% similarity threshold
    ocr_words = text_lower.split()

    for term in search_terms:
        term_clean = term.lower()
        if not term_clean:
            continue

        # A. Fuzzy word match
        matches = difflib.get_close_matches(term_clean, ocr_words, n=1, cutoff=threshold)
        if matches:
            return True

        # B. Prefix fallback (useful for long company names like "ACME Solutions Inc.")
        if len(term_clean) > 5:
            prefix = term_clean[:4]
            if prefix in text_lower:
                return True

    return False


def validate_ai_structure_response(
    response_json: Dict[str, Any],
    ocr_pages_list: List[str],
    private_id: Optional[IdentityProfile],
    business_id: Optional[IdentityProfile]
) -> List[str]:
    """
    Phase 105: Validates that the AI's structural decisions (tenant context)
    are plausible based on fuzzy identity matching.

    Args:
        response_json: The Stage 1 AI response.
        ocr_pages_list: List of full texts for each page.
        private_id: The user's private identity profile.
        business_id: The user's business identity profile.

    Returns:
        A list of validation error strings. Empty if no issues found.
    """
    errors: List[str] = []
    entities = response_json.get("detected_entities", [])
    if not isinstance(entities, list):
        return errors

    for ent in entities:
        if not isinstance(ent, dict):
            continue

        ctx = ent.get("tenant_context")
        pages = ent.get("page_indices", [])
        if not pages or not isinstance(pages, list):
            continue

        # Verify identity match for the first page of the logical document segment
        try:
            first_page_idx = int(pages[0]) - 1
            if first_page_idx < 0 or first_page_idx >= len(ocr_pages_list):
                continue
            first_page_text = ocr_pages_list[first_page_idx]
        except (ValueError, TypeError, IndexError):
            continue

        # Select profile to validate against
        target_profile = None
        is_business = (ctx == "BUSINESS")
        is_private = (ctx == "PRIVATE")
        
        if is_business:
            target_profile = business_id
        elif is_private:
            target_profile = private_id

        # 1. Profile Match Check (Gold Standard)
        match_found = False
        if target_profile:
            match_found = check_identity_fuzzy(first_page_text, target_profile)

        # 2. Heuristic Level 2: If no profile match, verify if the content at least looks like the context
        if not match_found:
            # Check for generic business markers if AI says BUSINESS
            if is_business:
                business_keywords = ["gmbh", "ag", "gbr", "kg", "inc", "ltd", "corp", "ust-idnr", "vat id", "rechnung", "invoice"]
                text_low = first_page_text.lower()
                if any(kw in text_low for kw in business_keywords):
                    match_found = True
                    # Optional: log that we matched based on generic markers
            
            # Check for name/person markers if AI says PRIVATE
            elif is_private:
                # Private is harder to verify generically, but we can check if it looks NOT like a business
                business_suffixes = ["gmbh", "ag", "gbr", "kg"]
                text_low = first_page_text.lower()
                if not any(kw in text_low for kw in business_suffixes):
                    # We are more lenient for PRIVATE if it doesn't look like a formal business doc
                    match_found = True

        # 3. Confidence Override: If AI is extremely sure and we have at least SOME text, trust it
        conf = ent.get("confidence", 0.0)
        if not match_found and conf >= 0.98 and len(first_page_text.strip()) > 50:
            match_found = True

        if not match_found and target_profile:
            errors.append(
                f"CONTEXT_ERROR: AI detected {ctx}, but no ZIP code or fuzzy address "
                f"match was found on Page {pages[0]}. Verification of Billing Address failed."
            )

        # 4. Direction Validation (Analytical)
        direction = ent.get("direction")
        if direction in ["INBOUND", "OUTBOUND"] and target_profile:
            # Simple check: If direction is set, but we couldn't find the identity in the text,
            # we should flag it so the Arbiter can double-check the visual role.
            if not match_found:
                errors.append(
                    f"DIRECTION_ERROR: AI detected {direction}, but user identity "
                    f"role could not be analytically verified on Page {pages[0]}."
                )

    return errors
