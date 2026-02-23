import ast
import os
import glob
import xml.etree.ElementTree as ET
import subprocess

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
TS_FILE = os.path.join(PROJECT_ROOT, 'resources/l10n/de/gui_strings.ts')
GUI_DIR = os.path.join(PROJECT_ROOT, 'gui')
CORE_DIR = os.path.join(PROJECT_ROOT, 'core')

class TranslationExtractor(ast.NodeVisitor):
    def __init__(self):
        self.context_strings = {} # {ClassName: {String}}
        self.current_class = None

    def visit_ClassDef(self, node):
        old_class = self.current_class
        self.current_class = node.name
        if node.name not in self.context_strings:
            self.context_strings[node.name] = set()
        self.generic_visit(node)
        self.current_class = old_class

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'tr':
            if node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    self.context_strings.setdefault(self.current_class, set()).add(arg.value)
                elif isinstance(arg, ast.Str): # Python < 3.8
                    self.context_strings.setdefault(self.current_class, set()).add(arg.s)
        
        # Support for QCoreApplication.translate("Context", "Text")
        elif isinstance(node.func, ast.Attribute) and node.func.attr == 'translate':
            # Check if it's called on QCoreApplication or similar
            if len(node.args) >= 2:
                ctx_arg = node.args[0]
                text_arg = node.args[1]
                
                ctx = None
                if isinstance(ctx_arg, ast.Constant) and isinstance(ctx_arg.value, str):
                    ctx = ctx_arg.value
                elif isinstance(ctx_arg, ast.Str):
                    ctx = ctx_arg.s
                    
                text = None
                if isinstance(text_arg, ast.Constant) and isinstance(text_arg.value, str):
                    text = text_arg.value
                elif isinstance(text_arg, ast.Str):
                    text = text_arg.s
                
                if ctx and text:
                    self.context_strings.setdefault(ctx, set()).add(text)

        self.generic_visit(node)

def extract_code_translations():
    extractor = TranslationExtractor()
    search_dirs = [GUI_DIR, CORE_DIR]
    for directory in search_dirs:
        for py_file in glob.glob(os.path.join(directory, '**/*.py'), recursive=True):
            with open(py_file, 'r', encoding='utf-8') as f:
                try:
                    tree = ast.parse(f.read())
                    extractor.visit(tree)
                except Exception as e:
                    print(f"Error parsing {py_file}: {e}")
    return extractor.context_strings

def sync_ts_file():
    print(f"Scanning code in {GUI_DIR}...")
    code_contexts = extract_code_translations()
    
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.parse(TS_FILE, parser=parser)
    root = tree.getroot()
    
    ts_contexts = {} # {Name: Element}
    translation_cache = {} # {source: {}}

    def harvest_from_xml(xml_content, name_for_log="current file"):
        nonlocal translation_cache
        try:
            h_root = ET.fromstring(xml_content)
        except Exception as e:
            print(f"Warning: Could not parse XML from {name_for_log}: {e}")
            return

        h_count = 0
        for ctx in h_root.findall('context'):
            for msg in ctx.findall('message'):
                src = msg.find('source')
                trans = msg.find('translation')
                if src is not None and src.text and trans is not None:
                    # Cache the translation
                    has_content = (trans.text and trans.text.strip()) or trans.findall('numerusform')
                    if not has_content: continue
                    
                    # Prefer finished translations
                    is_finished = trans.get('type') != 'unfinished'
                    if src.text not in translation_cache or is_finished:
                        data = {
                            'text': trans.text,
                            'type': trans.get('type'),
                            'numerus': msg.get('numerus'),
                            'forms': [nf.text for nf in trans.findall('numerusform')]
                        }
                        translation_cache[src.text] = data
                        h_count += 1
        print(f"Harvested {h_count} translations from {name_for_log}")

    # 1. Harvest from Git HEAD as baseline
    try:
        head_ts = subprocess.check_output(['git', 'show', 'HEAD:resources/l10n/de/gui_strings.ts'], stderr=subprocess.DEVNULL).decode('utf-8')
        harvest_from_xml(head_ts, "git HEAD")
    except Exception as e:
        print(f"Note: Could not harvest from Git HEAD: {e}")

    # 1b. Harvest from extra stable file if exists (recovered from deeper git history)
    STABLE_FILE = "/tmp/stable_ts.xml"
    if os.path.exists(STABLE_FILE):
        with open(STABLE_FILE, 'r', encoding='utf-8') as f:
            harvest_from_xml(f.read(), "stable baseline (/tmp/stable_ts.xml)")

    # 2. Harvest from current file (includes local unsaved changes)
    if os.path.exists(TS_FILE):
        with open(TS_FILE, 'r', encoding='utf-8') as f:
            harvest_from_xml(f.read(), "local TS file")

    # Now proceed with the actual sync
    with open(TS_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Clean content: remove everything after </TS>
    if "</TS>" in content:
        content = content[:content.find("</TS>") + 5]
    
    try:
        # Use simple fromstring to avoid issues with custom parser at this stage
        root = ET.fromstring(content)
        tree = ET.ElementTree(root)
    except Exception as e:
        print(f"Error parsing local TS file: {e}")
        # Fallback: create fresh TS structure if corrupted
        print("Falling back to fresh TS structure...")
        root = ET.Element( 'TS', version="2.1", language="de_DE")
        tree = ET.ElementTree(root)
    
    for context in root.findall('context'):
        name_elem = context.find('name')
        if name_elem is None: continue
        name = name_elem.text
        ts_contexts[name] = context
        
        # Harvest translations
        for msg in context.findall('message'):
            src = msg.find('source')
            trans = msg.find('translation')
            if src is not None and src.text and trans is not None:
                # Cache the translation
                has_content = (trans.text and trans.text.strip()) or trans.findall('numerusform')
                if not has_content: continue
                
                # Prefer finished translations
                is_finished = trans.get('type') != 'unfinished'
                if src.text not in translation_cache or is_finished:
                    data = {
                        'text': trans.text,
                        'type': trans.get('type'),
                        'numerus': msg.get('numerus'),
                        'forms': [nf.text for nf in trans.findall('numerusform')]
                    }
                    translation_cache[src.text] = data
        
    changes_made = False
    
    # 1. Update/Add Contexts
    for class_name, strings in code_contexts.items():
        if not strings:
            continue
            
        if class_name not in ts_contexts:
            print(f"Creating new context: {class_name}")
            new_ctx = ET.SubElement(root, 'context')
            name_elem = ET.SubElement(new_ctx, 'name')
            name_elem.text = class_name
            ts_contexts[class_name] = new_ctx
            changes_made = True
            
        ctx_element = ts_contexts[class_name]
        existing_messages = {} 
        for msg in ctx_element.findall('message'):
            src = msg.find('source')
            if src is not None and src.text:
                existing_messages[src.text] = msg
        
        # Add Missing or Repair Unfinished
        for s in strings:
            msg_elem = existing_messages.get(s)
            
            # If missing, create new
            if msg_elem is None:
                print(f"[{class_name}] Adding missing: '{s}'")
                msg_elem = ET.SubElement(ctx_element, 'message')
                src = ET.SubElement(msg_elem, 'source')
                src.text = s
                trans = ET.SubElement(msg_elem, 'translation')
                trans.set('type', 'unfinished')
                trans.text = ""
                existing_messages[s] = msg_elem
                changes_made = True
            
            # If unfinished, try to repair from cache
            trans = msg_elem.find('translation')
            if trans is not None and (trans.get('type') == 'unfinished' or not (trans.text and trans.text.strip() or trans.findall('numerusform'))):
                if s in translation_cache:
                    cached = translation_cache[s]
                    trans.text = cached['text']
                    if cached['type']:
                        trans.set('type', cached['type'])
                    else:
                        if 'type' in trans.attrib: del trans.attrib['type']
                        
                    if cached['numerus']:
                        msg_elem.set('numerus', cached['numerus'])
                    
                    # Handle Numerus Forms
                    for nf in trans.findall('numerusform'): trans.remove(nf) 
                    for f_text in cached['forms']:
                        nf = ET.SubElement(trans, 'numerusform')
                        nf.text = f_text
                        
                    print(f"  -> [{class_name}] Fixed/Filled: '{s}' using cached data.")
                    changes_made = True
                
        # Remove Obsolete strings
        for src_text, msg_elem in list(existing_messages.items()):
            if src_text not in strings:
                print(f"[{class_name}] Removing obsolete string: '{src_text}'")
                ctx_element.remove(msg_elem)
                changes_made = True

    # 2. Start Remove Orphaned Contexts (Strict Sync)
    # If a context is in TS but NOT in code, remove it entirely?
    # Test `test_no_obsolete_source_strings` checks strings.
    # If we keep an empty context, test shouldn't care?
    # But if context has strings, test will fail.
    
    # Collect valid code contexts keys
    valid_code_contexts = set(code_contexts.keys())
    
    for name, ctx_elem in list(ts_contexts.items()):
        if name not in valid_code_contexts:
            # Check if it has strings?
            # If it has strings, they are by definition obsolete (code doesn't use this class).
            has_strings = False
            for msg in ctx_elem.findall('message'):
                src = msg.find('source')
                if src is not None and src.text:
                    has_strings = True
                    break
            
            if has_strings:
                print(f"Removing obsolete context: {name}")
                root.remove(ctx_elem)
                changes_made = True
                
    if changes_made:
        print("Writing changes...")
        indent(root)
        tree.write(TS_FILE, encoding='utf-8', xml_declaration=True)
        print("Done.")
    else:
        print("No changes needed.")

def indent(elem, level=0):
    i = "\n" + level*"    "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "    "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for subelem in elem:
            indent(subelem, level+1)
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

if __name__ == "__main__":
    sync_ts_file()
