"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/rules_engine.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Unified Rule Engine for evaluating and applying tagging rules.
                Matches VirtualDocuments against FilterTree conditions to 
                automate document classification.
------------------------------------------------------------------------------
"""

from typing import TYPE_CHECKING, List, Optional, Set

if TYPE_CHECKING:
    from core.models.virtual import VirtualDocument

from core.database import DatabaseManager
from core.filter_tree import FilterNode, FilterTree


class RulesEngine:
    """
    Phase 106: Unified Rule Engine.
    Evaluates tagging rules defined in the FilterTree against documents.
    """

    def __init__(self, db: DatabaseManager, filter_tree: FilterTree) -> None:
        """
        Initializes the RulesEngine.

        Args:
            db: The database manager for evaluating conditions.
            filter_tree: The tree containing rule definitions.
        """
        self.db: DatabaseManager = db
        self.filter_tree: FilterTree = filter_tree

    def apply_rules_to_entity(self, v_doc: 'VirtualDocument', rules: Optional[List[FilterNode]] = None, only_auto: bool = True) -> bool:
        """
        Evaluate and apply all enabled rules from the FilterTree to a single VirtualDocument.

        Args:
            v_doc: The virtual document object to test and update.
            rules: Optional list of specific rules to evaluate. If None, fetches active rules from the tree.
            only_auto: If True, only apply rules marked as 'auto_apply'.

        Returns:
            True if tags were modified, False otherwise.
        """
        if rules is None:
            rules = self.filter_tree.get_active_rules(only_auto=only_auto)

        if not rules:
            return False

        # Use set for efficient tag operations
        current_tags: Set[str] = set(v_doc.tags or [])
        original_tags: Set[str] = current_tags.copy()
        
        new_workflow: Optional[str] = None
        modified = False

        for rule in rules:
            # Evaluate if the document matches the rule's filter criteria
            if self.db.matches_condition(v_doc.uuid, rule.data):
                # 1. Add specified tags
                if rule.tags_to_add:
                    current_tags.update(set(rule.tags_to_add))

                # 2. Remove specified tags
                if rule.tags_to_remove:
                    current_tags.difference_update(set(rule.tags_to_remove))
                
                # 3. Assign Workflow
                if rule.assign_workflow:
                    new_workflow = rule.assign_workflow

        # Check for tag changes
        if current_tags != original_tags:
            v_doc.tags = sorted(list(current_tags))
            modified = True
            
        # Check for workflow changes
        if new_workflow:
            if not v_doc.semantic_data:
                from core.models.semantic import SemanticExtraction
                v_doc.semantic_data = SemanticExtraction()
            
            if v_doc.semantic_data.workflow.rule_id != new_workflow:
                v_doc.semantic_data.workflow.rule_id = new_workflow
                modified = True

        return modified
