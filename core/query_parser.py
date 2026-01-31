"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/query_parser.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Simple natural language parser for search queries. Extracts 
                temporal constraints (years) and document types to generate 
                structured filter criteria.
------------------------------------------------------------------------------
"""

import re
from typing import Dict, Optional


class QueryParser:
    """
    Parses simple natural language queries into structured filter criteria.
    Focuses on keyword extraction for years and document types.
    """

    # Mapping of localized keywords to canonical document types
    KNOWN_TYPES: Dict[str, str] = {
        "invoice": "Invoice",
        "rechnung": "Invoice",
        "receipt": "Receipt",
        "quittung": "Receipt",
        "contract": "Contract",
        "vertrag": "Contract",
        "letter": "Letter",
        "brief": "Letter"
    }

    def parse(self, query: str) -> Dict[str, Optional[str]]:
        """
        Parses a query string into a structured criteria dictionary.

        Example:
            "Rechnungen 2023 Amazon" -> {
                'date_from': '2023-01-01',
                'date_to': '2023-12-31',
                'type': 'Invoice',
                'text_search': 'amazon'
            }

        Args:
            query: The natural language search query.

        Returns:
            A dictionary containing structured filter criteria.
        """
        criteria: Dict[str, Optional[str]] = {}
        tokens = query.lower().split()
        remaining_tokens = []

        # Year Extraction Pattern (2000-2099)
        year_pattern = re.compile(r"^(20\d{2})$")

        year_found = False
        type_found = False

        for token in tokens:
            # 1. Year Extraction
            if not year_found and year_pattern.match(token):
                year = token
                criteria['date_from'] = f"{year}-01-01"
                criteria['date_to'] = f"{year}-12-31"
                year_found = True
                continue

            # 2. Type Extraction (with simple fuzzy punctuation stripping)
            clean_token = token.rstrip("s.,;")
            if not type_found and clean_token in self.KNOWN_TYPES:
                criteria['type'] = self.KNOWN_TYPES[clean_token]
                type_found = True
                continue

            # 3. Collect non-metadata tokens for full-text search
            remaining_tokens.append(token)

        if remaining_tokens:
            criteria['text_search'] = " ".join(remaining_tokens)

        return criteria
