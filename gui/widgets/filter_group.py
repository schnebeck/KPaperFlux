
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QComboBox, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal
from gui.advanced_filter import FilterConditionWidget

class FilterGroupWidget(QWidget):
    """
    A container for a list of conditions (or nested groups) connected by a logical operator (AND/OR).
    Recursive structure.
    """
    remove_requested = pyqtSignal()
    changed = pyqtSignal()

    def __init__(self, parent=None, extra_keys=None, available_tags=None, is_root=False):
        super().__init__(parent)
        self.extra_keys = extra_keys
        self.available_tags = available_tags
        self.is_root = is_root
        
        # Style
        # Add a border or indentation to visualize grouping, but not for root
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)
        
        self.frame = QFrame()
        if not self.is_root:
            self.frame.setFrameShape(QFrame.Shape.StyledPanel)
            self.frame.setStyleSheet(".QFrame { border: 1px solid #CCC; border-radius: 4px; background-color: rgba(0,0,0,10); }")
        else:
            self.frame.setFrameShape(QFrame.Shape.NoFrame)
            
        self.layout = QVBoxLayout(self.frame)
        self.layout.setContentsMargins(8 if not is_root else 0, 8, 8, 8)
        
        # --- Header ---
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Logic Operator
        self.combo_logic = QComboBox()
        self.combo_logic.addItems(["AND (All)", "OR (Any)"])
        self.combo_logic.currentIndexChanged.connect(self.changed)
        header_layout.addWidget(self.combo_logic)
        
        header_layout.addStretch()
        
        # Buttons
        self.btn_add_condition = QPushButton(self.tr("+ Condition"))
        self.btn_add_condition.clicked.connect(self.add_condition)
        header_layout.addWidget(self.btn_add_condition)
        
        self.btn_add_group = QPushButton(self.tr("+ Group"))
        self.btn_add_group.clicked.connect(self.add_group)
        header_layout.addWidget(self.btn_add_group)
        
        if not self.is_root:
            self.btn_remove = QPushButton(self.tr("Remove Group"))
            self.btn_remove.setStyleSheet("color: red;")
            self.btn_remove.clicked.connect(self.remove_requested)
            header_layout.addWidget(self.btn_remove)
            
        self.layout.addLayout(header_layout)
        
        # --- Children Container ---
        self.children_container = QWidget()
        self.children_layout = QVBoxLayout(self.children_container)
        self.children_layout.setContentsMargins(10, 0, 0, 0) # Indent children
        self.layout.addWidget(self.children_container)
        self.layout.addStretch()
        
        self.main_layout.addWidget(self.frame)
        
        self.children_widgets = []

    def add_condition(self, data=None):
        child = FilterConditionWidget(self, extra_keys=self.extra_keys, available_tags=self.available_tags)
        if data:
            child.set_condition(data)
            
        self.children_layout.addWidget(child)
        self.children_widgets.append(child)
        
        child.remove_requested.connect(lambda: self.remove_child(child))
        child.changed.connect(self.changed)
        self.changed.emit()

    def add_group(self, data=None):
        child = FilterGroupWidget(self, extra_keys=self.extra_keys, available_tags=self.available_tags, is_root=False)
        if data:
            child.set_query(data)
            
        self.children_layout.addWidget(child)
        self.children_widgets.append(child)
        
        child.remove_requested.connect(lambda: self.remove_child(child))
        child.changed.connect(self.changed)
        self.changed.emit()

    def update_metadata(self, extra_keys, available_tags):
        """Recursively update metadata for all children."""
        self.extra_keys = extra_keys
        self.available_tags = available_tags
        for child in self.children_widgets:
             if hasattr(child, "update_metadata"):
                 child.update_metadata(extra_keys, available_tags)

    def remove_child(self, child_widget):
        if child_widget in self.children_widgets:
            self.children_widgets.remove(child_widget)
            self.children_layout.removeWidget(child_widget)
            child_widget.deleteLater()
            self.changed.emit()

    def clear(self):
        for child in list(self.children_widgets):
            self.remove_child(child)
            
    def get_query(self) -> dict:
        """
        Returns recursive dict:
        {
           "operator": "AND"|"OR",
           "conditions": [ {condition...}, {operator:..., conditions:[...]} ]
        }
        """
        logic = "AND" if self.combo_logic.currentIndex() == 0 else "OR"
        conditions = []
        
        for child in self.children_widgets:
            if isinstance(child, FilterConditionWidget):
                conditions.append(child.get_condition())
            elif isinstance(child, FilterGroupWidget):
                group_q = child.get_query()
                # If group is empty, skip it? Or allow empty groups (which do nothing)
                if group_q["conditions"]:
                    conditions.append(group_q)
                    
        return {
            "operator": logic,
            "conditions": conditions
        }

    def set_query(self, query: dict):
        """
        Rebuilds UI from query dict.
        """
        self.clear()
        
        # Set Logic
        op = query.get("operator", "AND").upper()
        idx = 1 if op == "OR" else 0
        self.combo_logic.setCurrentIndex(idx)
        
        # Add Children
        conditions = query.get("conditions", [])
        for item in conditions:
            if "operator" in item and "conditions" in item:
                # Is a Group
                self.add_group(item)
            else:
                # Is a Condition
                self.add_condition(item)
