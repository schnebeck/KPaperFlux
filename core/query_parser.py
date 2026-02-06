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
from datetime import datetime, timedelta
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
        Now supports relative time expressions:
        'heute', 'gestern', 'letzte woche', 'letzter monat', 'in 3 tagen'
        """
        criteria: Dict[str, Optional[str]] = {}
        tokens = query.lower().split()
        remaining_tokens = []

        year_pattern = re.compile(r"^(20\d{2})$")
        relative_days_pattern = re.compile(r"^in\s+(\d+)\s+tagen?$")
        
        full_query = query.lower()
        today = datetime.now().date()

        # 1. Check for bigger relative phrases first
        if "letzte woche" in full_query or "last week" in full_query:
            last_week = today - timedelta(days=7)
            criteria['date_from'] = last_week.isoformat()
            criteria['date_to'] = today.isoformat()
            full_query = full_query.replace("letzte woche", "").replace("last week", "")
        elif "letzter monat" in full_query or "last month" in full_query:
            last_month = today - timedelta(days=30)
            criteria['date_from'] = last_month.isoformat()
            criteria['date_to'] = today.isoformat()
            full_query = full_query.replace("letzter monat", "").replace("last month", "")
        elif "gestern" in full_query or "yesterday" in full_query:
            yesterday = today - timedelta(days=1)
            criteria['date_from'] = yesterday.isoformat()
            criteria['date_to'] = yesterday.isoformat()
            full_query = full_query.replace("gestern", "").replace("yesterday", "")
        elif "heute" in full_query or "today" in full_query:
            criteria['date_from'] = today.isoformat()
            criteria['date_to'] = today.isoformat()
            full_query = full_query.replace("heute", "").replace("today", "")

        # Check for "in X Tagen"
        match = re.search(r"in\s+(\d+)\s+tagen?", full_query)
        if match:
            days = int(match.group(1))
            target_date = today + timedelta(days=days)
            criteria['date_from'] = target_date.isoformat()
            criteria['date_to'] = target_date.isoformat()
            full_query = full_query.replace(match.group(0), "")

        # Process remaining tokens
        tokens = full_query.split()
        for token in tokens:
            # Year Extraction
            if year_pattern.match(token):
                year = token
                criteria['date_from'] = f"{year}-01-01"
                criteria['date_to'] = f"{year}-12-31"
                continue

            # Type Extraction
            clean_token = token.rstrip("s.,;")
            if clean_token in self.KNOWN_TYPES:
                criteria['type'] = self.KNOWN_TYPES[clean_token]
                continue

            remaining_tokens.append(token)

        if remaining_tokens:
            criteria['text_search'] = " ".join(remaining_tokens)

        return criteria
