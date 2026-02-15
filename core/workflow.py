
import os
import json
import logging
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

class WorkflowCondition(BaseModel):
    """Specific logical condition for a transition."""
    field: str
    op: str # >, <, >=, <=, =, !=
    value: Any

class WorkflowTransition(BaseModel):
    action: str
    target: str
    required_fields: List[str] = Field(default_factory=list)
    conditions: List[WorkflowCondition] = Field(default_factory=list)
    user_interaction: bool = False

class WorkflowState(BaseModel):
    label: str = ""
    transitions: List[WorkflowTransition] = Field(default_factory=list)
    final: bool = False

class WorkflowRule(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    states: Dict[str, WorkflowState] = Field(default_factory=dict)
    triggers: Dict[str, List[Any]] = Field(default_factory=dict)

class WorkflowEngine:
    def __init__(self, rule: WorkflowRule):
        self.rule = rule

    def get_next_state(self, current_state: str, action: str) -> str:
        state = self.rule.states.get(current_state)
        if not state:
            raise ValueError(f"State {current_state} not found in rule {self.rule.id}")
            
        for trans in state.transitions:
            if trans.action == action:
                return trans.target
                
        raise ValueError(f"Action {action} not allowed in state {current_state}")

    def can_transition(self, current_state: str, action: str, data: Dict[str, Any]) -> bool:
        state = self.rule.states.get(current_state)
        if not state:
            return False
            
        transition = next((t for t in state.transitions if t.action == action), None)
        if not transition:
            return False
            
        # 1. Check required fields (presence)
        for field in transition.required_fields:
            if field not in data or data[field] is None:
                return False

        # 2. Evaluate conditions (logic)
        for cond in transition.conditions:
            val = data.get(cond.field)
            if val is None: return False
            
            # Simple numeric or string comparison
            try:
                if cond.op == ">": 
                    if not (float(val) > float(cond.value)): return False
                elif cond.op == "<":
                    if not (float(val) < float(cond.value)): return False
                elif cond.op == ">=":
                    if not (float(val) >= float(cond.value)): return False
                elif cond.op == "<=":
                    if not (float(val) <= float(cond.value)): return False
                elif cond.op == "=":
                    if str(val) != str(cond.value): return False
                elif cond.op == "!=":
                    if str(val) == str(cond.value): return False
            except (ValueError, TypeError):
                # Fallback to string comparison if numeric fails
                if cond.op == "=":
                    if str(val) != str(cond.value): return False
                else:
                    return False
                
        return True

logger = logging.getLogger("KPaperFlux.Workflow")

class WorkflowRuleRegistry:
    """Singleton registry for managing document workflow rules."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(WorkflowRuleRegistry, cls).__new__(cls)
            cls._instance.rules = {}
        return cls._instance

    def load_from_directory(self, path: str):
        """Loads all .json files from the specified directory as rules."""
        self.rules.clear() # Reset cache to handle deleted files
        if not os.path.exists(path):
            logger.warning(f"Workflow directory not found: {path}")
            return

        for filename in os.listdir(path):
            if filename.endswith(".json"):
                full_path = os.path.join(path, filename)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        rule = WorkflowRule(**data)
                        self.rules[rule.id] = rule
                        logger.info(f"Loaded workflow rule: {rule.id}")
                except Exception as e:
                    logger.error(f"Failed to load rule from {filename}: {e}")

    def get_rule(self, rule_id: str) -> Optional[WorkflowRule]:
        return self.rules.get(rule_id)

    def find_rule_for_tags(self, tags: List[str]) -> Optional[WorkflowRule]:
        """Simple trigger-based lookup."""
        for rule in self.rules.values():
            trigger_tags = rule.triggers.get("type_tags", [])
            if any(t in tags for t in trigger_tags):
                return rule
        return None

    def list_rules(self) -> List[WorkflowRule]:
        """Returns all registered rules."""
        return list(self.rules.values())
