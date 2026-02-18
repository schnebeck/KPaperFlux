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

    def update_translation(self, context_name: str, source: str, translation: str, comment: str = None):
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
            if msg.findtext("source") == source and msg.findtext("comment") == comment:
                message = msg
                break
                
        if message is None:
            message = ET.SubElement(context, "message")
            source_elem = ET.SubElement(message, "source")
            source_elem.text = source
            if comment:
                comment_elem = ET.SubElement(message, "comment")
                comment_elem.text = comment
            trans_elem = ET.SubElement(message, "translation")
        else:
            trans_elem = message.find("translation")
            if trans_elem is None:
                trans_elem = ET.SubElement(message, "translation")
        
        if message.get("numerus") == "yes":
            # For numerus messages, we need <numerusform> children
            # Clear existing children/text
            trans_elem.text = None
            for child in list(trans_elem):
                trans_elem.remove(child)
            
            # For simplicity, we fill both forms (singular and plural) with the same translation
            # unless we want to support a list of translations.
            nf1 = ET.SubElement(trans_elem, "numerusform")
            nf1.text = translation
            nf2 = ET.SubElement(trans_elem, "numerusform")
            nf2.text = translation
        else:
            trans_elem.text = translation
            
        # Remove type="unfinished" if it exists
        if "type" in trans_elem.attrib:
            del trans_elem.attrib["type"]
            
        self._save_tree(tree)

    def deduplicate(self):
        tree = self._get_tree()
        root = tree.getroot()
        
        for context in root.findall("context"):
            seen = {} # (source, comment) -> message_elem
            messages = context.findall("message")
            for msg in messages:
                source = msg.findtext("source")
                comment = msg.findtext("comment")
                # If we have a duplicate, we keep the one that actually has a translation
                # or just the latest one.
                seen[(source, comment)] = msg
                context.remove(msg)
            
            # Add back unique ones
            for msg in seen.values():
                context.append(msg)
                
        self._save_tree(tree)

    def resolve_shortcuts_for_context(self, context_name: str, reserved: dict = None):
        """
        Assigns/Removes ampersand shortcuts based on the source string.
        Rule: 
        1. If source HAS a shortcut, translation MUST have one.
        2. If source HAS NO shortcut, translation MUST NOT have one (except literal &&).
        """
        tree = self._get_tree()
        root = tree.getroot()
        
        context = None
        for ctx in root.findall("context"):
            if ctx.findtext("name") == context_name:
                context = ctx
                break
        if context is None:
            return

        import re
        # Regex to match common placeholders: %s, %1, %-1.2f, {name}
        placeholder_pattern = re.compile(r"(%[\d\w.-]+|{[^{}]*})")

        def has_shortcut(text):
            if not text: return False
            idx = 0
            while True:
                idx = text.find("&", idx)
                if idx == -1 or idx == len(text) - 1: return False
                if text[idx+1] == "&":
                    idx += 2
                    continue
                if not text[idx+1].isalnum():
                    idx += 1
                    continue
                return True
        
        def get_shortcut_char(text):
            if not text: return None
            idx = 0
            while True:
                idx = text.find("&", idx)
                if idx == -1 or idx == len(text) - 1: return None
                if text[idx+1] == "&":
                    idx += 2
                    continue
                if not text[idx+1].isalnum():
                    idx += 1
                    continue
                return text[idx+1].lower()

        used_chars = set()
        messages = context.findall("message")
        
        # 1. Preliminary Scan: Collect reserved and existing shortcuts
        reserved_sources = set(reserved.keys()) if reserved else set()
        if reserved:
            for source, fixed_trans in reserved.items():
                char = get_shortcut_char(fixed_trans)
                if char:
                    used_chars.add(char)

        msg_states = [] 
        
        for msg in messages:
            source = msg.findtext("source")
            if source in reserved_sources:
                continue
            
            trans_elem = msg.find("translation")
            if trans_elem is None or not trans_elem.text:
                continue
            
            text = trans_elem.text
            # Replace single ampersands with double ampersands (literal) instead of stripping
            clean_text = re.sub(r"(?<!&)&(?!&)", "&&", text) 
            
            # Use source to decide if we SHOULD have a shortcut
            should_have_shortcut = has_shortcut(source)
            current_char = get_shortcut_char(text)
            
            if not should_have_shortcut:
                # Ensure no shortcut in translation (mask them as literal)
                trans_elem.text = clean_text
                continue # No further processing for plain items

            # If it SHOULD have a shortcut:
            if current_char:
                if current_char not in used_chars:
                    used_chars.add(current_char)
                else:
                    # Collision! Need re-assignment
                    current_char = None
            
            msg_states.append({
                "elem": msg,
                "source": source,
                "clean_text": clean_text,
                "current_char": current_char,
                "preferred_char": get_shortcut_char(source)
            })

        # 2. Assign shortcuts to those that need them
        for state in msg_states:
            if state["current_char"]:
                continue
            
            clean_text = state["clean_text"]
            forbidden_indices = set()
            for match in placeholder_pattern.finditer(clean_text):
                for i in range(match.start(), match.end()):
                    forbidden_indices.add(i)

            # Strategy: 1. Preferred from source, 2. First letters, 3. Consonants, 4. Vowels
            potential_chars = []
            if state["preferred_char"]:
                potential_chars.append(state["preferred_char"])
            
            # First alphabetic char
            m = re.search(r"[\w\d]", clean_text)
            if m:
                potential_chars.append(m.group(0).lower())
            
            # First letters of words
            for w in clean_text.split():
                m = re.search(r"[\w\d]", w)
                if m:
                    c = m.group(0).lower()
                    if c not in potential_chars: potential_chars.append(c)
            
            # Remaining
            for i, c in enumerate(clean_text):
                if c.isalnum():
                    cl = c.lower()
                    if cl not in potential_chars: potential_chars.append(cl)

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
            else:
                # Still no shortcut? Keep clean.
                state["elem"].find("translation").text = clean_text

        self._save_tree(tree)

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
