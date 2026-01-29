import json
from typing import List, Set, Optional
from core.database import DatabaseManager
from core.filter_tree import FilterTree, FilterNode


class RulesEngine:
    """
    Phase 106: Unified Rule Engine.
    Evaluates tagging rules defined in the FilterTree against documents.
    """
    def __init__(self, db: DatabaseManager, filter_tree: FilterTree):
        self.db = db
        self.filter_tree = filter_tree

    def apply_rules_to_entity(self, v_doc, rules: Optional[List[FilterNode]] = None, only_auto=True) -> bool:
        """
        Evaluate and apply all enabled rules from the FilterTree to a single VirtualDocument.
        Returns True if tags were modified.
        """
        if rules is None:
            rules = self.filter_tree.get_active_rules(only_auto=only_auto)
            
        if not rules:
            return False

        current_tags = set(v_doc.tags or [])
        original_tags = current_tags.copy()

        for rule in rules:
            # Note: rule is now a FilterNode
            if self.db.matches_condition(v_doc.uuid, rule.data):
                # 1. Add Tags
                if rule.tags_to_add:
                    current_tags.update(set(rule.tags_to_add))
                
                # 2. Remove Tags
                if rule.tags_to_remove:
                    current_tags.difference_update(set(rule.tags_to_remove))

        if current_tags != original_tags:
            v_doc.tags = sorted(list(current_tags))
            return True
            
        return False
