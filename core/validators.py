import difflib
from typing import List, Dict, Any, Optional
from core.models.identity import IdentityProfile

def check_identity_fuzzy(ocr_text: str, identity_profile: IdentityProfile) -> bool:
    """
    Validates an identity in the text.
    Priority 1: Zip code (Hard Match).
    Priority 2: Fuzzy text search (Soft Match).
    """
    if not identity_profile:
        return False
        
    text_lower = ocr_text.lower()
    
    # 1. ZIP/PLZ Check (Very reliable as numbers are often recognized well)
    # Extract zip from address_keywords
    for keyword in identity_profile.address_keywords:
        # We look for 5-digit numbers (German PLZ standard) or other keywords
        if keyword.isdigit() and len(keyword) == 5:
            if keyword in text_lower:
                return True # ZIP found -> Match!

    # 2. Fuzzy Text Check (If zip is missing or misread)
    search_terms = []
    if identity_profile.company_name:
        search_terms.append(identity_profile.company_name)
    
    # Collect text keywords (no pure numbers)
    search_terms += [k for k in identity_profile.address_keywords if not k.isdigit()]
    if identity_profile.name:
        search_terms.append(identity_profile.name)
    search_terms += identity_profile.aliases

    threshold = 0.6 # 60% similarity is enough (e.g. "Arbeitsstdt" vs "Arbeitsstadt")
    
    # Break OCR text into words for faster comparison
    ocr_words = text_lower.split()
    
    for term in search_terms:
        term_clean = term.lower()
        if not term_clean: continue
        
        # A. Search with difflib (Fuzzy)
        matches = difflib.get_close_matches(term_clean, ocr_words, n=1, cutoff=threshold)
        if matches:
            return True
            
        # B. Prefix search (for long words cutoff at the end)
        # "ACME Solu..." finds "ACME Solutions"
        if len(term_clean) > 5:
            prefix = term_clean[:4] # First 4 chars
            if prefix in text_lower:
                return True

    return False

def validate_ai_structure_response(response_json: Dict[str, Any], 
                                 ocr_pages_list: List[str],
                                 private_id: Optional[IdentityProfile],
                                 business_id: Optional[IdentityProfile]) -> List[str]:
    """
    Phase 105: Validates that the AI's context decision is plausible based on fuzzy matching.
    """
    errors = []
    entities = response_json.get("detected_entities", [])
    
    for ent in entities:
        ctx = ent.get("tenant_context")
        pages = ent.get("page_indices", [])
        if not pages: continue
        
        # We only check the first page of the entity for addresses (usually where it sits)
        try:
            first_page_idx = pages[0] - 1
            if first_page_idx < 0 or first_page_idx >= len(ocr_pages_list):
                continue
            first_page_text = ocr_pages_list[first_page_idx]
        except (IndexError, TypeError):
            continue
        
        target_profile = None
        if ctx == "BUSINESS":
            target_profile = business_id
        elif ctx == "PRIVATE":
            target_profile = private_id
            
        if target_profile:
            # Apply FUZZY CHECK
            if not check_identity_fuzzy(first_page_text, target_profile):
                errors.append(
                    f"CONTEXT_ERROR: AI detected {ctx}, but neither ZIP code nor fuzzy address match found in text on Page {pages[0]}. "
                    f"Check if Billing Address is visible."
                )

    return errors
