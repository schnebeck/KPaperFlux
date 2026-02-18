import xml.etree.ElementTree as ET
import os
from pathlib import Path

class L10nTool:
    def __init__(self, ts_path: str):
        self.ts_path = Path(ts_path)
        if not self.ts_path.exists():
            self._create_empty()
        
    def _create_empty(self):
        content = '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n<TS version="2.1" language="de">\n</TS>'
        self.ts_path.parent.mkdir(parents=True, exist_ok=True)
        self.ts_path.write_text(content, encoding="utf-8")

    def _get_tree(self):
        # We use a custom parser to handle possible whitespace issues if they occur
        return ET.parse(self.ts_path)

    def _save_tree(self, tree):
        root = tree.getroot()
        self._strip_whitespace(root)
        tree.write(self.ts_path, encoding="utf-8", xml_declaration=True)

    def _strip_whitespace(self, elem):
        """Recursively strip whitespace from tag text and tail."""
        if elem.text:
            elem.text = elem.text.strip()
        if elem.tail:
            elem.tail = elem.tail.strip()
        for child in elem:
            self._strip_whitespace(child)

    def update_translation(self, context_name: str, source: str, translation: str):
        tree = self._get_tree()
        root = tree.getroot()
        
        # Find context
        context = None
        for ctx in root.findall("context"):
            if ctx.findtext("name") == context_name:
                context = ctx
                break
        
        if context is None:
            context = ET.SubElement(root, "context")
            name_elem = ET.SubElement(context, "name")
            name_elem.text = context_name
            
        # Find message
        message = None
        for msg in context.findall("message"):
            if msg.findtext("source") == source:
                message = msg
                break
                
        if message is None:
            message = ET.SubElement(context, "message")
            source_elem = ET.SubElement(message, "source")
            source_elem.text = source
            trans_elem = ET.SubElement(message, "translation")
        else:
            trans_elem = message.find("translation")
            if trans_elem is None:
                trans_elem = ET.SubElement(message, "translation")
        
        trans_elem.text = translation
        # Remove type="unfinished" if it exists
        if "type" in trans_elem.attrib:
            del trans_elem.attrib["type"]
            
        self._save_tree(tree)

    def deduplicate(self):
        tree = self._get_tree()
        root = tree.getroot()
        
        for context in root.findall("context"):
            seen = {} # source -> message_elem
            messages = context.findall("message")
            for msg in messages:
                source = msg.findtext("source")
                # If we have a duplicate, we keep the one that actually has a translation
                # or just the latest one.
                seen[source] = msg
                context.remove(msg)
            
            # Add back unique ones
            for msg in seen.values():
                context.append(msg)
                
        self._save_tree(tree)

    def clean_format(self):
        """Fixes the weird whitespace/broken XML issues."""
        tree = self._get_tree()
        self._save_tree(tree)
