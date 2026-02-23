from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QComboBox, QLineEdit, QStackedWidget,
                             QMenu, QCheckBox, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QCoreApplication, QEvent

from core.logger import get_logger
logger = get_logger("gui.widgets.filter_condition")

# Mocks / Core Imports (angepasst für Standalone-Fähigkeit)
try:
    from core.metadata_normalizer import MetadataNormalizer
    from core.semantic_translator import SemanticTranslator
    from core.models.types import DocType
    from gui.widgets.multi_select_combo import MultiSelectComboBox
    from gui.widgets.date_range_picker import DateRangePicker
    from core.filter_token_registry import FilterTokenRegistry
except ImportError as e:
    import sys
    logger.error(f"Critical internal import failed in filter_condition.py: {e}")
    sys.exit(1)


class FilterConditionWidget(QWidget):
    """
    A single row representing a filter condition: [Field] [Operator] [Value] [Remove]
    """
    remove_requested = pyqtSignal()
    changed = pyqtSignal()

    @property
    def FIELDS(self):
        """Legacy compatibility for older tests."""
        registry = FilterTokenRegistry.instance()
        translator = SemanticTranslator.instance()
        return {t.id: translator.translate(t.label_key) for t in registry.get_all_tokens()}

    # Operators per type hint (simplified)
    OPERATORS = [
        ("Contains", "contains"),
        ("Equals", "equals"),
        ("Starts With", "starts_with"),
        ("Greater Than", "gt"),
        ("Less Than", "lt"),
        ("Is Empty", "is_empty"),
        ("Is Not Empty", "is_not_empty"),
        ("In List", "in"),
        ("Between", "between") # Added for ranges
    ]

    def __init__(self, parent=None, extra_keys=None, available_tags=None, available_system_tags=None, available_workflow_steps=None):
        super().__init__(parent)
        self.available_tags = available_tags or []
        self.available_system_tags = available_system_tags or []
        self.available_workflow_steps = available_workflow_steps or []
        self.extra_keys = extra_keys or []
        self.last_field = None
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # 1. Instantiate all Widgets
        self.btn_field_selector = QPushButton()
        self.btn_field_selector.setMinimumWidth(150)
        self.field_key = None
        self.field_name = None

        self.combo_op = QComboBox()
        self.combo_op.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.chk_negate = QCheckBox()
        self.input_stack = QStackedWidget()
        self.btn_remove = QPushButton("X")
        self.btn_remove.setFixedWidth(24)

        # 2. Setup Input Stack
        self.input_text = QLineEdit()
        self.input_stack.addWidget(self.input_text)
        self.input_multi = MultiSelectComboBox()
        self.input_stack.addWidget(self.input_multi)
        self.input_date = DateRangePicker()
        self.input_stack.addWidget(self.input_date)

        # 3. Add to Layout
        self.layout.addWidget(self.btn_field_selector, 1)
        self.layout.addWidget(self.chk_negate)
        self.layout.addWidget(self.combo_op)
        self.layout.addWidget(self.input_stack, 2)
        self.layout.addWidget(self.btn_remove)

        # 4. Connect Signals
        self.btn_field_selector.clicked.connect(self._show_field_menu)
        self.combo_op.currentIndexChanged.connect(self.changed)
        self.chk_negate.toggled.connect(self.changed)
        self.input_text.textChanged.connect(self.changed)
        self.input_multi.selectionChanged.connect(lambda: self.changed.emit())
        self.input_date.rangeChanged.connect(lambda: self.changed.emit())
        self.btn_remove.clicked.connect(self.remove_requested)
        
        self.retranslate_ui()

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
             self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        if not self.field_name:
            self.btn_field_selector.setText(self.tr("Select Field..."))
        else:
            # Phase 135: Token-driven label resolution
            registry = FilterTokenRegistry.instance()
            translator = SemanticTranslator.instance()
            token = registry.get_token(self.field_key)
            if token:
                display_name = translator.translate(token.label_key)
                self.btn_field_selector.setText(display_name)
            else:
                self.btn_field_selector.setText(self.field_name)

        self.chk_negate.setText(self.tr("Not"))
        
        # Populate Operators (Refresh)
        self.combo_op.blockSignals(True)
        old_op = self.combo_op.currentData()
        self.combo_op.clear()
        for name, key in self.OPERATORS:
            self.combo_op.addItem(self.tr(name), key)
        
        idx = self.combo_op.findData(old_op)
        if idx >= 0:
            self.combo_op.setCurrentIndex(idx)
        self.combo_op.blockSignals(False)

    def update_metadata(self, extra_keys=None, available_tags=None, available_system_tags=None, available_workflow_steps=None):
        """Update available keys/tags and refresh UI without losing state."""
        if extra_keys is not None: self.extra_keys = extra_keys
        if available_tags is not None: self.available_tags = available_tags
        if available_system_tags is not None: self.available_system_tags = available_system_tags
        if available_workflow_steps is not None: self.available_workflow_steps = available_workflow_steps

        # Refresh active input if it depends on tags
        if self.field_key in ["type_tags", "tags", "classification", "direction", "tenant_context"]:
             # Force a refresh of the multi-select combo items
             old_field = self.last_field
             self.last_field = None # Force it to re-populate
             self._on_field_changed(old_field)

    def _show_field_menu(self):
        menu = QMenu(self)
        registry = FilterTokenRegistry.instance()
        translator = SemanticTranslator.instance()

        # 1. Categories - Logic from registry
        categories = {
            "basis": ("📦 ", self.tr("Basis")),
            "ai": ("🤖 ", self.tr("Analysis")),
            "stamps": ("📑 ", self.tr("Stamps")),
            "sys": ("⚙️ ", self.tr("System")),
            "raw": ("🛠 ", self.tr("Raw Data"))
        }

        for cat_id, (icon, cat_label) in categories.items():
            display_label = icon + cat_label
            cat_menu = menu.addMenu(display_label)

            # Standard tokens from registry
            tokens = registry.get_tokens_by_category(cat_id)
            for t in tokens:
                label = translator.translate(t.label_key)
                action = cat_menu.addAction(label)
                action.triggered.connect(lambda checked, k=t.id, n=label: self._set_field(k, n))

            # Dynamic additions per category (Stamps)
            if cat_id == "stamps":
                has_stamps = False
                for k in self.extra_keys:
                    if k.startswith("stamp_field:"):
                        has_stamps = True
                        label = k[12:]
                        # Phase 135: Beautify and translate
                        display_name = translator.beautify_key(label)
                        action = cat_menu.addAction(self.tr("Field: %s") % display_name)
                        action.triggered.connect(lambda checked, k=k, n=display_name: self._set_field(k, n))
                if not has_stamps and not tokens:
                    cat_menu.setEnabled(False)

            elif cat_id == "ai":
                config = MetadataNormalizer.get_config() or {}
                for t_name, t_def in config.get("types", {}).items():
                    # Translated Type Name
                    label_key = t_def.get("label_key", f"type_{t_name.lower()}")
                    type_label = translator.translate(label_key)

                    type_menu = cat_menu.addMenu(type_label)
                    for f in t_def.get("fields", []):
                        for s in f.get("strategies", []):
                            if s["type"] == "json_path":
                                f_id = f["id"]
                                f_label_key = f.get("label_key", f_id)
                                f_label = translator.translate(f_label_key)

                                key = f"semantic:{s['path']}"
                                action = type_menu.addAction(f_label)
                                action.triggered.connect(lambda checked, k=key, n=f"{type_label} > {f_label}": self._set_field(k, n))

            elif cat_id == "raw":
                # Phase 135: Filter out keys already covered by other categories
                known_keys = set()
                # 1. Standard tokens and their semantic variations
                registry_ids = [t.id for t in registry.get_all_tokens()]
                for rid in registry_ids:
                    known_keys.add(rid)
                    known_keys.add(f"semantic:{rid}")
                    # Extra AI prefixes from extraction models
                    known_keys.add(f"ai_{rid}")
                    known_keys.add(f"semantic:ai_{rid}")

                # 2. AI Semantic fields from config
                config = MetadataNormalizer.get_config() or {}
                for t_name, t_def in config.get("types", {}).items():
                    for f in t_def.get("fields", []):
                        f_id = f["id"]
                        known_keys.add(f_id)
                        known_keys.add(f"semantic:{f_id}")
                        for s in f.get("strategies", []):
                            if s["type"] == "json_path":
                                p = s["path"]
                                known_keys.add(f"semantic:{p}")
                                known_keys.add(p)

                # Build nested menus for dotted keys
                # Filter out known keys and stamp fields
                raw_keys = [k for k in self.extra_keys if k not in known_keys and not k.startswith("stamp_field:")]
                sorted_keys = sorted(raw_keys)
                
                menus = {"": cat_menu}
                for k in sorted_keys:
                    parts = k.split(".")
                    # If it starts with semantic:, strip it for the menu structure if desired, 
                    # but here we keep the structure for DOT-navigation
                    
                    current_path = ""
                    for i in range(len(parts) - 1):
                        parent_path = current_path
                        part = parts[i]
                        # Beautify the folder name (Phase 135: Apply translator to all levels)
                        display_part = translator.beautify_key(part)
                        
                        current_path = f"{parent_path}.{part}" if parent_path else part
                        if current_path not in menus:
                            menus[current_path] = menus[parent_path].addMenu(display_part)
                    
                    # Add the final action
                    leaf_name = parts[-1]
                    display_leaf = translator.beautify_key(k).split(" > ")[-1]
                    
                    parent_path = ".".join(parts[:-1])
                    action = menus[parent_path].addAction(display_leaf)
                    action.triggered.connect(lambda checked, key=k, name=translator.beautify_key(k): self._set_field(key, name))

        menu.exec(self.btn_field_selector.mapToGlobal(self.btn_field_selector.rect().bottomLeft()))

    def _set_field(self, key, display_name):
        self.field_key = key
        self.field_name = display_name
        self.btn_field_selector.setText(display_name)
        self._on_field_changed(key)

    def _on_field_changed(self, field_key):
        if not field_key:
             return

        if field_key == self.last_field:
            return
        self.last_field = field_key

        # Logic to switch inputs
        if field_key in ["doc_date", "created_at", "last_processed_at", "last_used"]:
            self.input_stack.setCurrentIndex(2) # Date
        elif field_key in ["type_tags", "tags", "workflow_step"]:
            self.input_stack.setCurrentIndex(1) # Multi
            self.input_multi.clear()
            
            if field_key == "type_tags":
                self.input_multi.addItems(self.available_system_tags)
            elif field_key == "workflow_step":
                steps = self.available_workflow_steps
                if not steps: steps = ["NEW", "PAID", "URGENT", "REVIEW"] # Fallback
                self.input_multi.addItems(steps)
            else:
                self.input_multi.addItems(self.available_tags)
        elif field_key == "direction":
             self.input_stack.setCurrentIndex(1)
             self.input_multi.clear()
             # Direction is also derived from system tags (INBOUND/OUTBOUND)
             dirs = [t for t in self.available_system_tags if t in ["INBOUND", "OUTBOUND", "INTERNAL", "UNKNOWN"]]
             if not dirs: dirs = ["INBOUND", "OUTBOUND", "INTERNAL", "UNKNOWN"] # Fallback if DB empty
             self.input_multi.addItems(dirs)
        elif field_key == "tenant_context":
             self.input_stack.setCurrentIndex(1)
             self.input_multi.clear()
             ctxs = [t for t in self.available_system_tags if t.startswith("CTX_") or t in ["PRIVATE", "BUSINESS"]]
             if not ctxs: ctxs = ["PRIVATE", "BUSINESS", "UNKNOWN"]
             self.input_multi.addItems(ctxs)
        elif field_key == "classification":
             self.input_stack.setCurrentIndex(1)
             self.input_multi.clear()
             # Filter available_system_tags for things that are DocTypes
             allowed = {t.value for t in DocType}
             found_types = [t for t in self.available_system_tags if t in allowed]
             if not found_types: found_types = sorted(list(allowed)) # Fallback/Seed
             self.input_multi.addItems(found_types)
        elif field_key == "visual_audit_mode":
              self.input_stack.setCurrentIndex(1)
              self.input_multi.clear()
              self.input_multi.addItems(["STAMP_ONLY", "FULL_AUDIT", "NONE"])
        else:
            self.input_stack.setCurrentIndex(0) # Text

        self.changed.emit()

    def get_condition(self):
        field_key = self.field_key
        if not field_key:
             return None

        op = self.combo_op.currentData()

        # Get Value from active input
        idx = self.input_stack.currentIndex()
        val = None

        if op in ["is_empty", "is_not_empty"]:
            val = None
        elif idx == 0: # Text
            val = self.input_text.text()
            # If op is 'in' and text input, split by comma
            if op == "in" and val:
                 val = [x.strip() for x in val.split(",") if x.strip()]
        elif idx == 1: # Multi
            val = self.input_multi.getCheckedItems()
        elif idx == 2: # Date
            val = self.input_date.get_value()

        res = {"field": field_key, "op": op, "value": val, "negate": self.chk_negate.isChecked()}
        return res

    def set_condition(self, mode: dict):
        key = mode.get("field")
        if not key:
            return # Invalid condition data

        self.chk_negate.setChecked(mode.get("negate", False))

        # Phase 135: Resolve token to display name
        registry = FilterTokenRegistry.instance()
        translator = SemanticTranslator.instance()
        token = registry.get_token(key)
        
        display_name = key
        if token:
            display_name = translator.translate(token.label_key)
        elif key.startswith("semantic:"):
             path = key[9:]
             config = MetadataNormalizer.get_config() or {}
             for t_name, t_def in config.get("types", {}).items():
                 for f in t_def.get("fields", []):
                     for s in f.get("strategies", []):
                         if s["type"] == "json_path" and s["path"] == path:
                             f_label_key = f.get("label_key", f["id"])
                             f_label = translator.translate(f_label_key)
                             label_key = t_def.get("label_key", f"type_{t_name.lower()}")
                             type_label = translator.translate(label_key)
                             display_name = f"{type_label} > {f_label}"

        elif key.startswith("stamp_field:"):
             display_name = f"Stempel: {key[12:]}"
        else:
             # Phase 135: Beautify raw keys
             display_name = translator.beautify_key(key)

        self._set_field(key, display_name)

        # 2. Set Operator
        op = mode.get("op", "contains")
        idx = self.combo_op.findData(op)
        if idx >= 0: self.combo_op.setCurrentIndex(idx)

        # 3. Set Value
        val = mode.get("value")
        current_idx = self.input_stack.currentIndex()

        if current_idx == 0:
             if isinstance(val, list): val = ", ".join(map(str, val))
             self.input_text.setText(str(val) if val is not None else "")
        elif current_idx == 1:
             if isinstance(val, list):
                 self.input_multi.setCheckedItems(val)
             elif isinstance(val, str):
                 self.input_multi.setCheckedItems([val])
        elif current_idx == 2:
             self.input_date.set_value(val)
