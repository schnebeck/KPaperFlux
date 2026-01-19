
import json
import os
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

class TagDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.styles = self._load_styles()
        self.padding_x = 8
        self.padding_y = 2
        self.margin_right = 5

    def _load_styles(self):
        try:
            path = os.path.join(os.getcwd(), "resources", "tag_styles.json")
            if os.path.exists(path):
                with open(path, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading tag styles: {e}")
        
        return {
            "styles": {},
            "default": {
                "background": "#f4f4f5",
                "text": "#3f3f46",
                "border": "#d4d4d8"
            }
        }

    def _get_style(self, tag):
        # 1. Exact Match
        if tag in self.styles.get("styles", {}):
            return self.styles["styles"][tag]
        
        # 2. Wildcard Match (e.g. "todo:*")
        # We iterate over keys to find patterns
        for key, style in self.styles.get("styles", {}).items():
            if key.endswith("*"):
                prefix = key[:-1]
                if tag.startswith(prefix):
                    return style
        
        # 3. Default
        return self.styles.get("default", {})

    def paint(self, painter: QPainter, option, index):
        # Extract tags
        # The data should be the CSV string
        tag_string = index.data(Qt.ItemDataRole.DisplayRole)
        # Note: Usually we let super draw background if selected, but since we draw content custom:
        
        # Draw background if selected
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        if not tag_string:
            return 

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        tags = [t.strip() for t in tag_string.split(',') if t.strip()]
        
        # Geometry
        total_width = option.rect.width()
        current_x = option.rect.x() + 2
        
        # Height constraint: Center vertically, max 18px or row_height-4
        row_height = option.rect.height()
        pill_height = min(18, max(14, row_height - 4))
        y = option.rect.y() + (row_height - pill_height) / 2
        
        font = option.font
        font.setPointSize(font.pointSize() - 1)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        
        for i, tag in enumerate(tags):
            style = self._get_style(tag)
            display_text = tag
            
            # Simple Text width check
            text_width = metrics.horizontalAdvance(display_text)
            rect_width = text_width + (self.padding_x * 2)
            
            # Check boundaries
            # If we draw this pill, will it fit?
            # Also is it the last one? If not, we might need space for [+N]
            
            # Check if fits (Conservative)
            fits = (current_x + rect_width) < (option.rect.right() - 2)
            
            if not fits:
                # Overflow!
                remaining = len(tags) - i
                if remaining > 0:
                     badge = f"[+{remaining}]"
                     painter.setPen(option.palette.text().color())
                     # Draw badge if it fits? Usually yes.
                     # Just draw text, no pill, to discern from tags.
                     painter.drawText(QRectF(current_x, y, 40, pill_height), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, badge)
                break
                
            # Draw Pill
            bg_color = QColor(style.get("background", "white"))
            border_color = QColor(style.get("border", "gray"))
            text_color = QColor(style.get("text", "black"))
            
            rect = QRectF(current_x, y, rect_width, pill_height)
            
            painter.setPen(QPen(border_color))
            painter.setBrush(QBrush(bg_color))
            painter.drawRoundedRect(rect, 4, 4)
            
            painter.setPen(QPen(text_color))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, display_text)
            
            current_x += rect_width + self.margin_right
        
        painter.restore()
