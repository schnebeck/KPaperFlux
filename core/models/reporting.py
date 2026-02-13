
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

class Aggregation(BaseModel):
    field: str  # e.g. "amount", "tax_amount"
    op: str     # "sum", "avg", "count"

class ReportDefinition(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    filter_query: Dict[str, Any] = Field(default_factory=dict)
    group_by: Optional[str] = None # e.g. "doc_date:month", "sender", "type_tags"
    aggregations: List[Aggregation] = Field(default_factory=list)
    visualizations: List[str] = Field(default_factory=list) # "bar_chart", "table", "pie_chart", "csv"
