
from PyQt6.QtWidgets import QCompleter
from PyQt6.QtCore import Qt

class MultiTagCompleter(QCompleter):
    """
    QCompleter that supports comma-separated tags.
    Completes the last segment of the text.
    """
    def __init__(self, tags, parent=None):
        super().__init__(tags, parent)
        self.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        
    def pathFromIndex(self, index):
        path = super().pathFromIndex(index)
        return path

    def splitPath(self, path):
         if ',' in path:
             return [path.split(',')[-1].strip()]
         return [path.strip()]
