import xml.etree.ElementTree as ET
import os
from pathlib import Path
import re

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
        """
        Parses the TS file with an integrity check and retry logic.
        """
        import time
        max_retries = 5
        retry_delay = 0.2

        for attempt in range(max_retries):
            try:
                if not self.ts_path.exists():
                    self._create_empty()
                
                content = self.ts_path.read_text(encoding="utf-8").strip()
                if not content.endswith("</TS>"):
                    raise ValueError("TS file is incomplete (missing </TS> tag).")
                
                return ET.parse(self.ts_path)
            except (ET.ParseError, ValueError, IOError):
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                raise

        return ET.parse(self.ts_path)

    def _save_tree(self, tree):
        import tempfile
        root = tree.getroot()
        
        removed_broken = 0
        for context in root.findall("context"):
            for message in list(context.findall("message")):
                source_node = message.find("source")
                if source_node is None or not source_node.text or not source_node.text.strip():
                    context.remove(message)
                    removed_broken += 1
        
        if removed_broken > 0:
            print(f"[L10nTool] Pruned {removed_broken} invalid messages.")

        self._strip_whitespace(root)
        ET.indent(root, space="    ", level=0)
        
        fd, temp_path = tempfile.mkstemp(dir=self.ts_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, 'wb') as tmp:
                tree.write(tmp, encoding="utf-8", xml_declaration=True)
            
            try:
                ET.parse(temp_path)
            except Exception as e:
                raise IOError(f"Generated TS file is invalid: {e}")

            with open(temp_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content.endswith("</TS>"):
                    raise IOError("Failed to write complete TS file (missing </TS> tag).")
            
            os.replace(temp_path, self.ts_path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise IOError(f"Atomic write failed for {self.ts_path}: {e}")

    def _strip_whitespace(self, elem):
        if elem.text:
            stripped = elem.text.strip()
            elem.text = stripped if stripped else None
        if elem.tail:
            stripped = elem.tail.strip()
            elem.tail = stripped if stripped else None
            
        for child in elem:
            self._strip_whitespace(child)

    def update_translation(self, context_name: str, source: str, translation: str, comment: str = None):
        tree = self._get_tree()
        root = tree.getroot()
        
        context = None
        for ctx in root.findall("context"):
            if ctx.findtext("name") == context_name:
                context = ctx
                break
        
        if context is None:
            context = ET.SubElement(root, "context")
            name_elem = ET.SubElement(context, "name")
            name_elem.text = context_name
            
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
            trans_elem.text = None
            for child in list(trans_elem):
                trans_elem.remove(child)
            
            nf1 = ET.SubElement(trans_elem, "numerusform")
            nf1.text = translation
            nf2 = ET.SubElement(trans_elem, "numerusform")
            nf2.text = translation
        else:
            trans_elem.text = translation
            
        if "type" in trans_elem.attrib:
            del trans_elem.attrib["type"]
            
        self._save_tree(tree)

    def deduplicate(self):
        """
        Removes messsages with duplicate source/comment within the same context,
        keeping only the last occurrence.
        """
        tree = self._get_tree()
        root = tree.getroot()
        
        for context in root.findall("context"):
            seen = {} # (source, comment) -> message_elem
            messages = list(context.findall("message"))
            for msg in messages:
                source = msg.findtext("source")
                comment = msg.findtext("comment")
                key = (source, comment)
                if key in seen:
                    context.remove(seen[key])
                seen[key] = msg
        
        self._save_tree(tree)

    def resolve_shortcuts_for_context(self, context_name: str, reserved: dict = None):
        tree = self._get_tree()
        root = tree.getroot()
        
        context = None
        for ctx in root.findall("context"):
            if ctx.findtext("name") == context_name:
                context = ctx
                break
        if context is None:
            return

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

        def strip_shortcuts(text):
            if not text: return ""
            res = []
            i = 0
            while i < len(text):
                if text[i] == "&":
                    if i + 1 < len(text):
                        if text[i+1] == "&":
                            res.append("&")
                            i += 2
                        elif text[i+1].isalnum():
                            # Mnemonic! Skip the &
                            i += 1
                        else:
                            # Probably a literal & followed by space/punct (e.g. "Save & Exit")
                            res.append("&")
                            i += 1
                    else:
                        # Trailing &
                        i += 1
                else:
                    res.append(text[i])
                    i += 1
            return "".join(res)
            
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
            if msg.get("numerus") == "yes":
                continue
                
            source = msg.findtext("source")
            trans_elem = msg.find("translation")
            if trans_elem is None or not trans_elem.text:
                continue
            
            text = trans_elem.text
            should_have_shortcut = has_shortcut(source)
            current_char = get_shortcut_char(text)
            
            # If it's a reserved string, we don't touch it but we still record its char
            if source in reserved_sources:
                if current_char: used_chars.add(current_char)
                continue

            if not should_have_shortcut:
                # Ensure every single & is escaped to &&
                res = []
                i = 0
                while i < len(text):
                    if text[i] == "&":
                        if i + 1 < len(text) and text[i+1] == "&":
                            res.append("&&")
                            i += 2
                        else:
                            res.append("&&")
                            i += 1
                    else:
                        res.append(text[i])
                        i += 1
                trans_elem.text = "".join(res)
                continue

            # Shortcut IS wanted.
            if current_char:
                if current_char not in used_chars:
                    used_chars.add(current_char)
                else:
                    current_char = None
            
            msg_states.append({
                "elem": msg,
                "source": source,
                "clean_base": strip_shortcuts(text),
                "current_char": current_char,
                "preferred_char": get_shortcut_char(source)
            })

        # 2. Assign shortcuts to those that need them
        for state in msg_states:
            if state["current_char"]:
                continue
            
            clean_text = state["clean_base"]
            forbidden_indices = set()
            for match in placeholder_pattern.finditer(clean_text):
                for i in range(match.start(), match.end()):
                    forbidden_indices.add(i)

            potential_chars = []
            if state["preferred_char"]:
                potential_chars.append(state["preferred_char"])
            
            m = re.search(r"[\w\d]", clean_text)
            if m:
                potential_chars.append(m.group(0).lower())
            
            for w in clean_text.split():
                m_word = re.search(r"[\w\d]", w)
                if m_word:
                    c = m_word.group(0).lower()
                    if c not in potential_chars: potential_chars.append(c)
            
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
                state["elem"].find("translation").text = clean_text.replace("&", "&&")

        self._save_tree(tree)

    def check_shortcut_collisions(self):
        tree = self._get_tree()
        root = tree.getroot()
        collisions = {}

        for context in root.findall("context"):
            ctx_name = context.findtext("name")
            shortcuts = {}
            
            for msg in context.findall("message"):
                trans_elem = msg.find("translation")
                if trans_elem is not None and trans_elem.text:
                    text = trans_elem.text
                    idx = 0
                    while True:
                        idx = text.find("&", idx)
                        if idx == -1 or idx == len(text) - 1:
                            break
                        
                        char = text[idx+1].lower()
                        if char == "&": 
                            idx += 2
                            continue
                        
                        source = msg.findtext("source")
                        if char not in shortcuts:
                            shortcuts[char] = []
                        shortcuts[char].append(f"'{source}' (-> '{text}')")
                        idx += 2

            ctx_collisions = {char: sources for char, sources in shortcuts.items() if len(sources) > 1}
            if ctx_collisions:
                collisions[ctx_name] = ctx_collisions

        return collisions

class MasterMappingTool:
    """
    Programmatic editor for tools/fill_l10n.py to avoid manual syntax errors.
    """
    def __init__(self, mapping_path: str = None):
        if mapping_path is None:
            # Default to fellow tool directory
            mapping_path = Path(__file__).parent / "fill_l10n.py"
        self.path = Path(mapping_path)

    def update_common(self, source: str, translation: str):
        content = self.path.read_text(encoding="utf-8")
        
        # Simple regex to find the common dict entries. 
        # Note: This assumes a specific formatting style (key: value,)
        pattern = re.compile(rf'"{re.escape(source)}":\s*".*?",')
        replacement = f'"{source}": "{translation}",'
        
        if pattern.search(content):
            new_content = pattern.sub(replacement, content)
        else:
            # Add to the beginning of the common dict (after the comment)
            insertion_point = content.find("# Menus & Actions")
            if insertion_point == -1: insertion_point = content.find("common = {") + 10
            else: insertion_point = content.find("\n", insertion_point) + 1
            
            new_content = content[:insertion_point] + f'        "{source}": "{translation}",\n' + content[insertion_point:]
            
        self.path.write_text(new_content, encoding="utf-8")

    def update_context_override(self, context: str, source: str, translation: str):
        content = self.path.read_text(encoding="utf-8")
        
        # 1. Identify the 'contexts = {' block
        # We look for the block starting with 4 spaces '    contexts = {' 
        # and ending with 4 spaces '    }'
        ctx_dict_match = re.search(r"    contexts = \{(.*?)\n    \}", content, re.DOTALL)
        if not ctx_dict_match:
            # Fallback if it's not indented (top level)
            ctx_dict_match = re.search(r"contexts = \{(.*?)\n\}", content, re.DOTALL)
            
        if not ctx_dict_match:
            raise ValueError("Could not find contexts dictionary in fill_l10n.py")
            
        ctx_dict_content = ctx_dict_match.group(1)
        
        # 2. Check if context already exists
        # We need to be careful with nested dictionaries. 
        # We look for the context name followed by optional whitespace and a brace
        ctx_pattern = re.compile(rf'"{re.escape(context)}":\s*\{{(.*?)\n\s*\}}\s*,', re.DOTALL)
        match = ctx_pattern.search(ctx_dict_content)
        
        if match:
            inner_content = match.group(1)
            line_pattern = re.compile(rf'"{re.escape(source)}":\s*".*?",')
            line_replacement = f'"{source}": "{translation}",'
            
            if line_pattern.search(inner_content):
                new_inner = line_pattern.sub(line_replacement, inner_content)
                new_content = content.replace(inner_content, new_inner)
            else:
                # Add to end of context block
                new_inner = inner_content + f'            "{source}": "{translation}",\n'
                new_content = content.replace(inner_content, new_inner)
        else:
            # Create new context block INSIDE the contexts dict
            new_ctx_block = f'        "{context}": {{\n            "{source}": "{translation}",\n        }},\n    '
            # Insert before the closing brace of the contexts dict
            # Use the end of the match group 1 (the content area)
            insertion_point = ctx_dict_match.start(1) + len(ctx_dict_content)
            
            new_content = content[:insertion_point] + new_ctx_block + content[insertion_point:]
                
        self.path.write_text(new_content, encoding="utf-8")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="KPaperFlux L10n Management Tool")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Change command
    change_parser = subparsers.add_parser("change", help="Update a translation mapping in fill_l10n.py")
    change_parser.add_argument("--src", required=True, help="Source string (English)")
    change_parser.add_argument("--trans", required=True, help="Target translation (German)")
    change_parser.add_argument("--ctx", help="Optional context name (if omitted, updates 'common')")
    change_parser.add_argument("--sync", action="store_true", help="Automatically run full synchronization after update")

    args = parser.parse_args()

    if args.command == "change":
        mapper = MasterMappingTool()
        if args.ctx:
            print(f"Updating context '{args.ctx}': '{args.src}' -> '{args.trans}'")
            mapper.update_context_override(args.ctx, args.src, args.trans)
        else:
            print(f"Updating common: '{args.src}' -> '{args.trans}'")
            mapper.update_common(args.src, args.trans)
        
        if args.sync:
            print("Running full synchronization...")
            import subprocess
            # 1. pylupdate (to catch any new tr calls)
            # Find files (simplified)
            root = Path(__file__).parent.parent
            subprocess.run(["pylupdate6", "gui", "core", "plugins", "-ts", "resources/l10n/de/gui_strings.ts"], cwd=root)
            # 2. fill_l10n
            subprocess.run(["python3", "tools/fill_l10n.py"], cwd=root)
            # 3. lrelease
            subprocess.run(["lrelease", "resources/l10n/de/gui_strings.ts"], cwd=root)
            print("Sync complete.")

if __name__ == "__main__":
    main()
