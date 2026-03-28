"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/filter_token_registry.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Central registry for all filterable fields (tokens).
                Ensures language-agnostic storage of filter rules.
------------------------------------------------------------------------------
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class FilterToken:
    id: str
    category: str
    label_key: str
    data_type: str  # "string", "date", "amount", "list"
    icon: str = ""

class FilterTokenRegistry:
    """
    Registry for language-agnostic filter tokens.
    """
    _instance: Optional['FilterTokenRegistry'] = None

    def __init__(self):
        self._tokens: Dict[str, FilterToken] = {}
        self._setup_standard_tokens()

    @classmethod
    def instance(cls) -> 'FilterTokenRegistry':
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def register(self, token: FilterToken):
        self._tokens[token.id] = token

    def get_token(self, token_id: str) -> Optional[FilterToken]:
        return self._tokens.get(token_id)

    def get_all_tokens(self) -> List[FilterToken]:
        return list(self._tokens.values())

    def get_tokens_by_category(self, category: str) -> List[FilterToken]:
        return [t for t in self._tokens.values() if t.category == category]

    def _setup_standard_tokens(self):
        # Basis
        basis_tokens = [
            FilterToken("doc_date", "basis", "field_doc_date", "date", "📅 "),
            FilterToken("classification", "basis", "field_classification", "list", "📁 "),
            FilterToken("status", "basis", "field_status", "list", "🚦 "),
            FilterToken("tags", "basis", "field_tags", "list", "🏷️ "),
            FilterToken("type_tags", "basis", "field_type_tags", "list", "🏷️ "),
            FilterToken("workflow_step", "basis", "field_workflow_step", "list", "⚙️ "),
            FilterToken("cached_full_text", "basis", "field_full_text", "string", "📄 "),
        ]
        
        # AI
        ai_tokens = [
            FilterToken("direction", "ai", "field_direction", "list", "➡️ "),
            FilterToken("tenant_context", "ai", "field_tenant_context", "list", "👤 "),
            FilterToken("confidence", "ai", "field_ai_confidence", "amount", "🎯 "),
            FilterToken("reasoning", "ai", "field_ai_reasoning", "string", "🧠 "),
        ]
        
        # Stamps
        stamp_tokens = [
            FilterToken("stamp_text", "stamps", "field_stamp_text_total", "string", "📑 "),
            FilterToken("stamp_type", "stamps", "field_stamp_type", "list", "📑 "),
            FilterToken("visual_audit_mode", "stamps", "field_audit_mode", "list", "📑 "),
        ]
        
        # System
        sys_tokens = [
            FilterToken("original_filename", "sys", "field_filename", "string", "📁 "),
            FilterToken("page_count_virt", "sys", "field_pages", "amount", "📄 "),
            FilterToken("uuid", "sys", "field_uuid", "string", "🆔 "),
            FilterToken("created_at", "sys", "field_created_at", "date", "⏰ "),
            FilterToken("last_processed_at", "sys", "field_processed_at", "date", "⏰ "),
            FilterToken("last_used", "sys", "field_last_used", "date", "⏰ "),
            FilterToken("deleted_at", "sys", "field_deleted_at", "date", "⏰ "),
            FilterToken("locked_at", "sys", "field_locked_at", "date", "⏰ "),
            FilterToken("exported_at", "sys", "field_exported_at", "date", "⏰ "),
            FilterToken("archived", "sys", "field_archived", "list", "📦 "),
            FilterToken("deleted", "sys", "field_in_trash", "list", "🗑️ "),
        ]

        # Deadline
        deadline_tokens = [
            FilterToken("expiry_date", "deadline", "field_expiry_date", "date", "⏳ "),
            FilterToken("due_date", "deadline", "field_due_date", "date", "📅 "),
            FilterToken("service_period_end", "deadline", "field_service_period_end", "date", "📅 "),
        ]

        for t in basis_tokens + ai_tokens + stamp_tokens + sys_tokens + deadline_tokens:
            self.register(t)
