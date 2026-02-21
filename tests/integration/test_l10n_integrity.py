import pytest
import xml.etree.ElementTree as ET
from pathlib import Path
from tools.l10n_tool import L10nTool

def test_production_ts_integrity():
    """
    Scans the actual resources/l10n/de/gui_strings.ts for errors.
    """
    ts_path = Path("resources/l10n/de/gui_strings.ts")
    if not ts_path.exists():
        pytest.skip("Production TS file not found")
        
    tool = L10nTool(str(ts_path))
    
    # 1. Check for shortcut collisions
    collisions = tool.check_shortcut_collisions()
    
    error_msgs = []
    for context, ctx_collisions in collisions.items():
        for char, sources in ctx_collisions.items():
            error_msgs.append(f"Collision in {context} for '&{char}': {', '.join(sources)}")
            
    # 2. Check for broken ampersands (e.g. '& ' or '&' at end)
    tree = tool._get_tree()
    root = tree.getroot()
    for context in root.findall("context"):
        ctx_name = context.findtext("name")
        for msg in context.findall("message"):
            source = msg.findtext("source")
            trans_elem = msg.find("translation")
            if trans_elem is not None and trans_elem.text:
                text = trans_elem.text
                
                # Check for standalone & (not followed by & or alnum)
                # Note: This is a bit tricky due to Qt's double-ampersand rule
                i = 0
                while i < len(text):
                    if text[i] == "&":
                        if i + 1 >= len(text):
                            error_msgs.append(f"Trailing '&' in {ctx_name}: '{text}' (source: '{source}')")
                        elif text[i+1] == " ":
                            error_msgs.append(f"Ampersand followed by space in {ctx_name}: '{text}' (source: '{source}')")
                        elif text[i+1] == "&":
                            i += 2
                            continue
                        elif not text[i+1].isalnum():
                            error_msgs.append(f"Ampersand followed by non-alphanumeric '{text[i+1]}' in {ctx_name}: '{text}' (source: '{source}')")
                    i += 1

    if error_msgs:
        pytest.fail("L10n Integrity Errors:\n" + "\n".join(error_msgs))

def test_no_empty_finished_translations():
    """
    Ensures that all translations marked as finished (no 'type') actually have text.
    """
    ts_path = Path("resources/l10n/de/gui_strings.ts")
    if not ts_path.exists():
        pytest.skip("Production TS file not found")
        
    tree = ET.parse(ts_path)
    root = tree.getroot()
    
    failures = []
    for msg in root.findall(".//message"):
        trans = msg.find("translation")
        if trans is not None:
            if "type" not in trans.attrib: # Finished
                # Check for direct text OR numerus forms
                has_text = False
                if trans.text and trans.text.strip():
                    has_text = True
                else:
                    for nf in trans.findall("numerusform"):
                        if nf.text and nf.text.strip():
                            has_text = True
                            break
                
                if not has_text:
                    source = msg.findtext("source")
                    failures.append(f"Empty finished translation for source: '{source}'")
                    
    if failures:
        pytest.fail("Found finished translations without text:\n" + "\n".join(failures[:20]))
