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
        Assigns unique ampersand shortcuts to messages in a context.
        Strategy:
        1. Keep existing shortcuts that are already in the XML (if they don't collide).
        2. Keep reserved shortcuts from 'reserved' dict.
        3. Assign new shortcuts ONLY to items that need them and don't have them.
        4. STRIP shortcuts from items that shouldn't have them (tooltips, placeholders).
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

        import re
        # Regex to match common placeholders: %s, %1, %-1.2f, {name}
        placeholder_pattern = re.compile(r"(%[\d\w.-]+|{[^{}]*})")

        used_chars = set()
        messages = context.findall("message")
        
        # 1. Preliminary Scan: Collect all EXISTING and RESERVED shortcuts
        # We also identify messages that need processing.
        msg_states = [] # list of (msg_elem, source, clean_text, current_char, should_have_shortcut)
        
        # Track reserved chars first and exclude them from auto-processing
        reserved_sources = set(reserved.keys()) if reserved else set()
        if reserved:
            for source, fixed_trans in reserved.items():
                idx = fixed_trans.find("&")
                if idx != -1 and idx < len(fixed_trans) - 1 and fixed_trans[idx+1] != "&":
                    used_chars.add(fixed_trans[idx+1].lower())

        for msg in messages:
            source = msg.findtext("source")
            if source in reserved_sources:
                continue # Skip reserved items, they are already handled in used_chars
            
            trans_elem = msg.find("translation")
            if trans_elem is None or not trans_elem.text:
                continue
            
            text = trans_elem.text
            # Heuristic: Identify strings that should NOT have shortcuts
            is_tooltip = len(source) > 30 or source.strip().endswith(".")
            is_placeholder = source.startswith("---")
            is_label = source.strip().endswith(":")
            # Also check if it's an icon-only string or just a number
            is_minimal = len(source.strip()) < 2 and not source.isalnum()
            
            should_have_shortcut = not (is_tooltip or is_placeholder or is_label or is_minimal)
            
            # Find current shortcut
            current_char = None
            idx = 0
            while True:
                idx = text.find("&", idx)
                if idx == -1 or idx == len(text) - 1: break
                if text[idx+1] == "&":
                    idx += 2
                    continue
                current_char = text[idx+1].lower()
                break
            
            clean_text = re.sub(r"(?<!&)&(?!&)", "", text)
            
            if should_have_shortcut and current_char:
                if current_char not in used_chars:
                    used_chars.add(current_char)
                else:
                    # Collision! We'll need to re-assign this one.
                    current_char = None
            elif not should_have_shortcut and current_char:
                # Strip unwanted shortcut immediately
                trans_elem.text = clean_text
                current_char = None

            msg_states.append({
                "elem": msg,
                "source": source,
                "clean_text": clean_text,
                "current_char": current_char,
                "should_have": should_have_shortcut
            })

        # 2. Main Scan: Assign shortcuts to messages that need them but don't have them
        for state in msg_states:
            if not state["should_have"] or state["current_char"]:
                continue
            
            clean_text = state["clean_text"]
            # Identify forbidden indices
            forbidden_indices = set()
            for match in placeholder_pattern.finditer(clean_text):
                for i in range(match.start(), match.end()):
                    forbidden_indices.add(i)

            potential_chars = []
            
            # Strategy 1: First letters
            # Prioritize first letter of first word
            if clean_text:
                m = re.search(r"[\w\d]", clean_text)
                if m:
                    char = m.group(0).lower()
                    potential_chars.append(char)
            
            words = clean_text.split()
            for w in words:
                m = re.search(r"[\w\d]", w)
                if m:
                    char = m.group(0).lower()
                    if char not in potential_chars: potential_chars.append(char)
            
            # Strategy 2: Consonants
            consonants = "bcdfghjkmnpqrstvwxyzß" 
            for c in clean_text:
                c_low = c.lower()
                if c_low in consonants and c_low not in ["l", "i"] and c_low not in potential_chars:
                    potential_chars.append(c_low)
            
            # Strategy 3: Vowels
            vowels = "aeiouäöü"
            for c in clean_text:
                c_low = c.lower()
                if c_low in vowels and c_low != "i" and c_low not in potential_chars:
                    potential_chars.append(c_low)

            # Fallback
            for i, c in enumerate(clean_text):
                if c.isalnum() and c.lower() not in potential_chars:
                    potential_chars.append(c.lower())

            # Find first available that is NOT in a forbidden position
            # AND not already in used_chars
            found_char = None
            found_idx = -1
            for char in potential_chars:
                if char not in used_chars:
                    for i, c in enumerate(clean_text):
                        if c.lower() == char and i not in forbidden_indices:
                            found_char = char
                            found_idx = i
                            break
                    if found_char: break
            
            if found_char and found_idx != -1:
                used_chars.add(found_char)
                new_text = clean_text[:found_idx] + "&" + clean_text[found_idx:]
                state["elem"].find("translation").text = new_text
                state["current_char"] = found_char
            else:
                # No shortcut found, strip any that might have been there
                state["elem"].find("translation").text = clean_text

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
