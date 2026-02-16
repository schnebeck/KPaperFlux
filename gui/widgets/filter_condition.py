from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QComboBox, QLineEdit, QStackedWidget,
                             QMenu, QCheckBox, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal

# Mocks / Core Imports (angepasst für Standalone-Fähigkeit)
try:
    from core.metadata_normalizer import MetadataNormalizer
    from core.semantic_translator import SemanticTranslator
    from core.models.types import DocType
    from gui.widgets.multi_select_combo import MultiSelectComboBox
    from gui.widgets.date_range_picker import DateRangePicker
except ImportError:
    # Mocks, falls Core nicht verfügbar
    class MetadataNormalizer:
        @staticmethod
        def get_config(): return {}
    class SemanticTranslator:
        @staticmethod
        def instance():
             class Dummy:
                 def translate(self, x): return x
             return Dummy()
    class DocType:
        INVOICE = "invoice"
        RECEIPT = "receipt"
        CONTRACT = "contract"
    class MultiSelectComboBox(QComboBox):
        selectionChanged = pyqtSignal()
        def getCheckedItems(self): return []
        def setCheckedItems(self, i): pass
    class DateRangePicker(QWidget):
        rangeChanged = pyqtSignal()
        def get_value(self): return None
        def set_value(self, v): pass


class FilterConditionWidget(QWidget):
    """
    A single row representing a filter condition: [Field] [Operator] [Value] [Remove]
    """
    remove_requested = pyqtSignal()
    changed = pyqtSignal()

    CATEGORIES = {
        "basis": "Basis",
        "ai": "Analysis",
        "stamps": "Stamps",
        "sys": "System",
        "raw": "Raw Data"
    }

    FIELDS_BY_CAT = {
        "basis": {
            "Document Date": "doc_date",
            "Classification": "classification",
            "Status": "status",
            "Tags": "tags",
            "System Tags": "type_tags",
            "Workflow Step": "workflow_step",
            "Full Text": "cached_full_text",
        },
        "ai": {
            "Direction": "direction",
            "Context": "tenant_context",
            "AI Confidence": "confidence",
            "AI Reasoning": "reasoning",
        },
        "stamps": {
            "Stamp Text (Total)": "stamp_text",
            "Stamp Type": "stamp_type",
            "Audit Mode": "visual_audit_mode",
        },
        "sys": {
            "Filename": "original_filename",
            "Pages": "page_count_virt",
            "UUID": "uuid",
            "Created At": "created_at",
            "Processed At": "last_processed_at",
            "In Trash": "deleted",
        }
    }

    # Flat mapping for internal use / tests
    FIELDS = {}
    for cat in FIELDS_BY_CAT.values():
        for label, val in cat.items():
            FIELDS[val] = label

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
        self.btn_field_selector = QPushButton(self.tr("Select Field..."))
        self.btn_field_selector.setMinimumWidth(150)
        self.field_key = None
        self.field_name = None

        self.combo_op = QComboBox()
        self.chk_negate = QCheckBox(self.tr("Not"))
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

        # 3. Populate Operators
        for name, key in self.OPERATORS:
            self.combo_op.addItem(self.tr(name), key)

        # 4. Add to Layout
        self.layout.addWidget(self.btn_field_selector, 1)
        self.layout.addWidget(self.chk_negate)
        self.layout.addWidget(self.combo_op, 1)
        self.layout.addWidget(self.input_stack, 2)
        self.layout.addWidget(self.btn_remove)

        # 5. Connect Signals (AFTER creating widgets!)
        self.btn_field_selector.clicked.connect(self._show_field_menu)
        self.combo_op.currentIndexChanged.connect(self.changed)
        self.chk_negate.toggled.connect(self.changed)
        self.input_text.textChanged.connect(self.changed)
        self.input_multi.selectionChanged.connect(lambda: self.changed.emit())
        self.input_date.rangeChanged.connect(lambda: self.changed.emit())
        self.btn_remove.clicked.connect(self.remove_requested)

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
        translator = SemanticTranslator.instance()

        # 1. Categories
        for cat_id, cat_label in self.CATEGORIES.items():
            # Apply icon based on ID
            icons = {"basis": "📦 ", "ai": "🤖 ", "stamps": "📑 ", "sys": "⚙️ ", "raw": "🛠 "}
            display_label = icons.get(cat_id, "") + self.tr(cat_label)
            cat_menu = menu.addMenu(display_label)

            # Basis fields
            fields = self.FIELDS_BY_CAT.get(cat_id, {})
            for name, key in fields.items():
                action = cat_menu.addAction(self.tr(name))
                action.triggered.connect(lambda checked, k=key, n=self.tr(name): self._set_field(k, n))

            # Dynamic additions per category
            if cat_id == "stamps":
                has_stamps = False
                for k in self.extra_keys:
                    if k.startswith("stamp_field:"):
                        has_stamps = True
                        label = k[12:]
                        action = cat_menu.addAction(self.tr("Field: %s") % label)
                        action.triggered.connect(lambda checked, k=k, n=label: self._set_field(k, n))
                if not has_stamps and not fields:
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
                # Build nested menus for dotted keys (e.g. summary.tax.total)
                sorted_keys = sorted([k for k in self.extra_keys if not k.startswith("stamp_field:")])

                # Dictionary to store created menus to avoid duplicates
                # Base is the cat_menu
                menus = {"": cat_menu}

                for k in sorted_keys:
                    parts = k.split(".")
                    current_path = ""

                    # Create parent menus if needed
                    for i in range(len(parts) - 1):
                        parent_path = current_path
                        part = parts[i]
                        current_path = f"{parent_path}.{part}" if parent_path else part

                        if current_path not in menus:
                            menus[current_path] = menus[parent_path].addMenu(part)

                    # Add the final action
                    leaf_name = parts[-1]
                    parent_path = ".".join(parts[:-1])
                    action = menus[parent_path].addAction(leaf_name)
                    action.triggered.connect(lambda checked, key=k, name=k: self._set_field(key, name))

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

        # Determine Display Name for the button
        display_name = key

        # Search in static mappings
        for cat, fields in self.FIELDS_BY_CAT.items():
            for name, k in fields.items():
                if k == key:
                    display_name = name
                    break

        # Search in AI schema
        if key.startswith("semantic:"):
             path = key[9:]
             config = MetadataNormalizer.get_config() or {}
             for t_name, t_def in config.get("types", {}).items():
                 for f in t_def.get("fields", []):
                     for s in f.get("strategies", []):
                         if s["type"] == "json_path" and s["path"] == path:
                             display_name = f"{t_name} > {f['id']}"

        # Search in Dynamic Stamps
        if key.startswith("stamp_field:"):
             display_name = f"Stempel: {key[12:]}"

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
