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
        ET.indent(root, space="    ", level=0)
        tree.write(self.ts_path, encoding="utf-8", xml_declaration=True)

    def _strip_whitespace(self, elem):
        """Recursively strip whitespace from tag text and tail."""
        if elem.text:
            stripped = elem.text.strip()
            # If it was just whitespace, make it empty
            elem.text = stripped if stripped else None
        if elem.tail:
            stripped = elem.tail.strip()
            elem.tail = stripped if stripped else None
            
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

    def resolve_shortcuts_for_context(self, context_name: str, reserved: dict = None):
        """
        Automatically assigns unique ampersand shortcuts for all messages in a context.
        Follows KDE/Qt HIG principles:
        1. Try first letter of first word.
        2. Try first letter of other words.
        3. Try other consonants (prefer uppercase).
        4. Try vowels.
        Vermeidet 'i' und 'l' wenn möglich.
        """
        tree = self._get_tree()
        root = tree.getroot()
        
        context = None
        for ctx in root.findall("context"):
            if ctx.findtext("name") == context_name:
                context = ctx
                break
        if not context:
            return

        used_chars = set()
        messages = context.findall("message")
        
        # 1. First, find all existing shortcuts we want to KEEP
        # This includes everything in 'reserved' and anything already assigned
        # that we shouldn't touch? 
        # Actually, let's be aggressive: We re-assign everything NOT in reserved.
        
        fixed_assignments = {} # id -> char
        
        if reserved:
            for source, fixed_trans in reserved.items():
                idx = fixed_trans.find("&")
                if idx != -1 and idx < len(fixed_trans) - 1:
                    char = fixed_trans[idx+1].lower()
                    used_chars.add(char)
                    # We store this to skip these messages later
                    fixed_assignments[source] = char

        messages_to_process = []
        for msg in messages:
            source = msg.findtext("source")
            if source in fixed_assignments:
                continue
            
            trans_elem = msg.find("translation")
            if trans_elem is not None and trans_elem.text:
                # If it already has a shortcut but is NOT reserved, we track it
                # BUT we will re-assign it to ensure optimality across the context.
                # Actually, if we want to be less invasive, we ONLY assign to those without.
                # But the user wants "conflict resolution".
                messages_to_process.append(msg)

        # 2. Process messages
        import re
        # Regex to match common placeholders: %s, %1, %-1.2f, {name}
        placeholder_pattern = re.compile(r"(%[\d\w.-]+|{[^{}]*})")

        for msg in messages_to_process:
            trans_elem = msg.find("translation")
            text = trans_elem.text
            # Strip existing '&' (but keep &&)
            clean_text = re.sub(r"(?<!&)&(?!&)", "", text)
            
            # Identify forbidden indices (indices that are part of a placeholder)
            forbidden_indices = set()
            for match in placeholder_pattern.finditer(clean_text):
                for i in range(match.start(), match.end()):
                    forbidden_indices.add(i)

            words = clean_text.split()
            potential_chars = []
            
            # HIG Strategy 1: First letters of words
            for w in words:
                m = re.search(r"[\w\d]", w)
                if m:
                    char = m.group(0).lower()
                    if char not in potential_chars:
                        potential_chars.append(char)
            
            # HIG Strategy 2: Consonants (prefer case-distinguishable)
            consonants = "bcdfghjkmnpqrstvwxyzß" 
            for c in clean_text:
                c_low = c.lower()
                if c_low in consonants and c_low not in ["l", "i"] and c_low not in potential_chars:
                    potential_chars.append(c_low)
            
            # HIG Strategy 3: Vowels (prefer not 'i')
            vowels = "aeiouäöü"
            for c in clean_text:
                c_low = c.lower()
                if c_low in vowels and c_low != "i" and c_low not in potential_chars:
                    potential_chars.append(c_low)

            # Fallback
            for c in ["l", "i"]:
                if c in clean_text.lower() and c not in potential_chars:
                    potential_chars.append(c)
            
            # Final fallback: any character left
            for i, c in enumerate(clean_text):
                if c.isalnum() and c.lower() not in potential_chars:
                    potential_chars.append(c.lower())

            # Find first available that is NOT in a forbidden position
            found_char = None
            found_idx = -1
            
            for char in potential_chars:
                if char not in used_chars:
                    # Check if this character exists in a non-forbidden position
                    for i, c in enumerate(clean_text):
                        if c.lower() == char and i not in forbidden_indices:
                            found_char = char
                            found_idx = i
                            break
                    if found_char:
                        break
            
            if found_char and found_idx != -1:
                used_chars.add(found_char)
                new_text = clean_text[:found_idx] + "&" + clean_text[found_idx:]
                trans_elem.text = new_text
            else:
                # No shortcut found (rare) or all potential chars are in placeholders
                trans_elem.text = clean_text

        self._save_tree(tree)

    def check_shortcut_collisions(self):
        """
        Checks for duplicate ampersand shortcuts within each context.
        Returns a dict of context_name -> list of (shortcut, source_list).
        """
        tree = self._get_tree()
        root = tree.getroot()
        collisions = {}

        for context in root.findall("context"):
            ctx_name = context.findtext("name")
            shortcuts = {} # char.lower() -> list of sources
            
            for msg in context.findall("message"):
                trans_elem = msg.find("translation")
                if trans_elem is not None and trans_elem.text:
                    text = trans_elem.text
                    # Find all occurrences of &
                    idx = 0
                    while True:
                        idx = text.find("&", idx)
                        if idx == -1 or idx == len(text) - 1:
                            break
                        
                        char = text[idx+1].lower()
                        if char == "&": # Escaped ampersand "&&"
                            idx += 2
                            continue
                        
                        source = msg.findtext("source")
                        if char not in shortcuts:
                            shortcuts[char] = []
                        shortcuts[char].append(f"'{source}' (-> '{text}')")
                        idx += 2

            # Filter for duplicates
            ctx_collisions = {char: sources for char, sources in shortcuts.items() if len(sources) > 1}
            if ctx_collisions:
                collisions[ctx_name] = ctx_collisions

        return collisions

    def clean_format(self):
        """Fixes the weird whitespace/broken XML issues."""
        tree = self._get_tree()
        self._save_tree(tree)
