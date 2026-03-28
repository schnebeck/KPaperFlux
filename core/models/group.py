"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/group.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    DocumentGroup model for user-defined document grouping.
                Groups form an optional hierarchy (parent_id) and are
                manually assigned to documents via a membership table.
                filter_query is reserved for future partial-automation.
------------------------------------------------------------------------------
"""
from typing import Optional
from pydantic import BaseModel, Field


class DocumentGroup(BaseModel):
    """Named group that can contain any number of virtual documents."""
    id: str
    name: str
    parent_id: Optional[str] = None
    color: Optional[str] = None       # hex color, e.g. "#2563eb"
    icon: Optional[str] = None        # emoji, e.g. "📁"
    description: Optional[str] = None
    sort_order: int = 0
    filter_query: Optional[dict] = None  # reserved: future auto-membership
