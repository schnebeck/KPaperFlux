"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/reporting.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Pydantic models of report definitions: aggregations, visual
                components and the definition itself.
------------------------------------------------------------------------------
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

class Aggregation(BaseModel):
    field: str  # e.g. "amount", "tax_amount"
    op: str     # "sum", "avg", "count"

class ReportComponent(BaseModel):
    type: str  # "bar_chart", "pie_chart", "line_chart", "table", "text"
    content: Optional[str] = None # Used for text blocks
    settings: Dict[str, Any] = Field(default_factory=dict)

class ReportDefinition(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    filter_query: Dict[str, Any] = Field(default_factory=dict)
    group_by: Optional[str] = None 
    aggregations: List[Aggregation] = Field(default_factory=list)
    visualizations: List[str] = Field(default_factory=list) # Legacy/Fallback
    components: List[ReportComponent] = Field(default_factory=list)
