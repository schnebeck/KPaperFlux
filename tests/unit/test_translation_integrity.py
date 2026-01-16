import pytest
import xml.etree.ElementTree as ET
import os
import glob
import re

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
TS_FILE = os.path.join(PROJECT_ROOT, 'resources/translations/kpaperflux_de.ts')
GUI_DIR = os.path.join(PROJECT_ROOT, 'gui')

import ast

class TranslationVisitor(ast.NodeVisitor):
    def __init__(self):
        self.strings = set()
        
    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'tr':
            if node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    self.strings.add(arg.value)
        self.generic_visit(node)

def extract_tr_strings_from_code():
    """
    Scans all .py files in gui/ directory using AST.
    Returns a set of found source strings.
    """
    found_strings = set()
    files = glob.glob(os.path.join(GUI_DIR, '**/*.py'), recursive=True)
    
    for file_path in files:
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                tree = ast.parse(f.read())
                visitor = TranslationVisitor()
                visitor.visit(tree)
                found_strings.update(visitor.strings)
            except Exception as e:
                print(f"Failed to parse {file_path}: {e}")
                
    return found_strings

def extract_source_strings_from_ts():
    """
    Parses the TS file and returns a set of source strings.
    """
    if not os.path.exists(TS_FILE):
        return set()
        
    tree = ET.parse(TS_FILE)
    root = tree.getroot()
    
    ts_strings = set()
    for context in root.findall('context'):
        for message in context.findall('message'):
            source = message.find('source')
            if source is not None and source.text:
                ts_strings.add(source.text)
                
    return ts_strings

def test_no_missing_source_strings():
    """
    Ensures that every tr() call in the code has a corresponding <source> entry in the TS file.
    """
    code_strings = extract_tr_strings_from_code()
    ts_strings = extract_source_strings_from_ts()
    
    # We allow some flexibility? No, strict is better for now.
    # But wait, f-strings inside tr() like tr(f"...") are bad practice but might exist.
    # The regex captures the raw string inside tr("..."). 
    # If code has tr(f"Foo {bar}"), regex sees f"Foo {bar}" ?? No, tr("...") usually implies static string.
    # If dynamic: tr(f"...") -> the key is the dynamic string which is impossible to match static TS.
    # Let's see what failures we get.
    
    missing = code_strings - ts_strings
    
    # Filter out known false positives or non-static strings if any
    # e.g. strings containing { } might be handled differently if TS has them.
    
    assert not missing, f"Found {len(missing)} strings in code missing from TS file:\n" + "\n".join(sorted(list(missing))[:20])

def test_no_obsolete_source_strings():
    """
    Ensures that every <source> entry in the TS file is actually used in the code.
    Catches typos like 'E &xit' in TS when code has 'E&xit'.
    """
    code_strings = extract_tr_strings_from_code()
    ts_strings = extract_source_strings_from_ts()
    
    obsolete = ts_strings - code_strings
    
    # Common exceptions: 
    # - Strings generated dynamically (bad practice but possible)
    # - Strings from .ui files (we don't use .ui files, pure python)
    # - Strings in core/ (we only scanned gui/) -> ScannerDialog might check core?
    # Let's assume strict check for now.
    
    assert not obsolete, f"Found {len(obsolete)} strings in TS file not found in code (Potential Typos/Obsolete):\n" + "\n".join(sorted(list(obsolete))[:20])
