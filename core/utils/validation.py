"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/utils/validation.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Utility functions for validating document metadata like IBANs.
------------------------------------------------------------------------------
"""

import re

def validate_iban(iban: str) -> bool:
    """
    Validates an IBAN according to ISO 13616.
    
    Args:
        iban: The IBAN string to validate.
        
    Returns:
        True if the IBAN is valid, False otherwise.
    """
    if not iban:
        return False
        
    # Remove all non-alphanumeric characters
    iban = re.sub(r'[^A-Z0-9]', '', iban.upper())
    
    # Check length (minimum 4, maximum 34)
    if not (4 <= len(iban) <= 34):
        return False
        
    # Reassemble: Move first 4 chars to the end
    rearranged = iban[4:] + iban[:4]
    
    # Replace letters with digits (A=10, B=11, ..., Z=35)
    numeric_iban = ""
    for char in rearranged:
        if char.isdigit():
            numeric_iban += char
        else:
            numeric_iban += str(ord(char) - 55)
            
    # Check modulo 97
    try:
        return int(numeric_iban) % 97 == 1
    except ValueError:
        return False

def validate_bic(bic: str) -> bool:
    """
    Performs a simple regex check for BIC (8 or 11 characters).
    """
    if not bic:
        return False
    return bool(re.match(r'^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$', bic.upper()))
