import json
from dataclasses import dataclass, field
from typing import List, Set, Optional
from core.database import DatabaseManager

@dataclass
class TaggingRule:
    id: Optional[int] = None
    name: str = ""
    filter_conditions: dict = field(default_factory=dict)
    tags_to_add: List[str] = field(default_factory=list)
    tags_to_remove: List[str] = field(default_factory=list)
    is_enabled: bool = True
    execution_order: int = 0
    auto_apply: bool = True

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row[0],
            name=row[1],
            filter_conditions=json.loads(row[2]),
            tags_to_add=json.loads(row[3]),
            tags_to_remove=json.loads(row[4] or '[]'),
            is_enabled=bool(row[5]),
            execution_order=row[6],
            auto_apply=bool(row[7]) if len(row) > 7 else True
        )

class RulesEngine:
    """
    Phase 106: The brain behind automated document categorization.
    Evaluates tagging rules against document entities and modifies their type_tags.
    """
    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_enabled_rules(self, only_auto=False) -> List[TaggingRule]:
        cursor = self.db.connection.cursor()
        sql = "SELECT id, name, filter_conditions, tags_to_add, tags_to_remove, is_enabled, execution_order, auto_apply FROM tagging_rules WHERE is_enabled = 1"
        if only_auto:
            sql += " AND auto_apply = 1"
        sql += " ORDER BY execution_order ASC"
        
        cursor.execute(sql)
        return [TaggingRule.from_row(row) for row in cursor.fetchall()]

    def apply_rules_to_entity(self, v_doc, rules: Optional[List[TaggingRule]] = None, only_auto=False) -> bool:
        """
        Evaluate and apply all enabled rules to a single VirtualDocument.
        Returns True if tags were modified.
        """
        if rules is None:
            rules = self.get_enabled_rules(only_auto=only_auto)
            
        if not rules:
            return False

        # Use Sets for idempotency (sets automatically handle duplicates)
        current_tags = set(v_doc.type_tags or [])
        original_tags = current_tags.copy()

        for rule in rules:
            if self.db.matches_condition(v_doc.uuid, rule.filter_conditions):
                # 1. Add Tags
                add_set = set(rule.tags_to_add)
                current_tags.update(add_set)
                
                # 2. Remove Tags
                if rule.tags_to_remove:
                    remove_set = set(rule.tags_to_remove)
                    current_tags.difference_update(remove_set)

        if current_tags != original_tags:
            v_doc.type_tags = sorted(list(current_tags))
            return True
            
        return False
