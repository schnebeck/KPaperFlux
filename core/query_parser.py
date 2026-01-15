
import re
from datetime import date

class QueryParser:
    """
    Parses natural language queries into filter criteria.
    """
    
    KNOWN_TYPES = {
        "invoice": "Invoice",
        "rechnung": "Invoice",
        "receipt": "Receipt",
        "quittung": "Receipt",
        "contract": "Contract",
        "vertrag": "Contract",
        "letter": "Letter",
        "brief": "Letter"
    }
    
    def parse(self, query: str) -> dict:
        """
        Parse query string into criteria dict.
        Returns: {
            'date_from': 'YYYY-MM-DD',
            'date_to': 'YYYY-MM-DD',
            'type': 'Invoice',
            'text_search': 'amazon'
        }
        """
        criteria = {}
        tokens = query.lower().split()
        remaining_tokens = []
        
        # 1. Year Extraction (2000-2099)
        year_found = False
        year_pattern = re.compile(r"^(20\d{2})$")
        
        # 2. Type Extraction
        type_found = None
        
        for token in tokens:
            # Check Year
            if not year_found and year_pattern.match(token):
                year = int(token)
                criteria['date_from'] = f"{year}-01-01"
                criteria['date_to'] = f"{year}-12-31"
                year_found = True
                continue
                
            # Check Type
            clean_token = token.rstrip("s.,") # Simple plural/punct strip
            if not type_found and clean_token in self.KNOWN_TYPES:
                criteria['type'] = self.KNOWN_TYPES[clean_token]
                type_found = True
                continue
                
            remaining_tokens.append(token)
            
        # 3. Remaining Text
        if remaining_tokens:
            criteria['text_search'] = " ".join(remaining_tokens)
            
        return criteria
