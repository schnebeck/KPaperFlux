from typing import List, Optional
from pydantic import BaseModel

class IdentityProfile(BaseModel):
    """
    Structured Identity Profile extracted from a raw signature.
    Used for intelligent direction classification.
    """
    name: Optional[str] = None # Official Name (Person or Entity)
    aliases: List[str] = []    # Variations for the main name
    
    # Explicit Company Fields (if present)
    company_name: Optional[str] = None
    company_aliases: List[str] = []
    
    address_keywords: List[str] = [] # Atomic parts (Street, City, Zip)
    vat_id: Optional[str] = None
    iban: List[str] = []
