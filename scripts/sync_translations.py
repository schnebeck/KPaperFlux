import ast
import os
import glob
import xml.etree.ElementTree as ET

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
TS_FILE = os.path.join(PROJECT_ROOT, 'resources/translations/kpaperflux_de.ts')
GUI_DIR = os.path.join(PROJECT_ROOT, 'gui')

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
        self.generic_visit(node)

def extract_code_translations():
    extractor = TranslationExtractor()
    for py_file in glob.glob(os.path.join(GUI_DIR, '**/*.py'), recursive=True):
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
    for context in root.findall('context'):
        name = context.find('name').text
        ts_contexts[name] = context
        
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
        
        # Add Missing
        for s in strings:
            if s not in existing_messages:
                print(f"[{class_name}] Adding missing: '{s}'")
                new_msg = ET.SubElement(ctx_element, 'message')
                src = ET.SubElement(new_msg, 'source')
                src.text = s
                trans = ET.SubElement(new_msg, 'translation')
                trans.set('type', 'unfinished')
                trans.text = "" 
                existing_messages[s] = new_msg
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
