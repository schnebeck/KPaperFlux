import pytest
import xml.etree.ElementTree as ET
import os

TS_FILE = os.path.join(os.path.dirname(__file__), '../../resources/l10n/de/gui_strings.ts')

def test_translation_file_exists():
    assert os.path.exists(TS_FILE), f"Translation file not found at {TS_FILE}"

def test_translation_formatting():
    """
    Ensures that <source> and <translation> tags do not have leading/trailing whitespace 
    in their text content.
    """
    tree = ET.parse(TS_FILE)
    root = tree.getroot()
    
    errors = []
    
    for context in root.findall('context'):
        context_name = context.find('name').text
        for message in context.findall('message'):
            source = message.find('source')
            translation = message.find('translation')
            
            if source is not None and source.text:
                if source.text != source.text.strip():
                    errors.append(f"Context '{context_name}': Source '{source.text}' has surrounding whitespace.")
            
            if translation is not None:
                # If there are children (plurals), check the children instead of container text
                children = list(translation)
                if children:
                    for child in children:
                        if child.text and child.text != child.text.strip():
                            errors.append(f"Context '{context_name}': {child.tag} '{child.text}' has surrounding whitespace.")
                elif translation.text:
                    if translation.text != translation.text.strip():
                        errors.append(f"Context '{context_name}': Translation '{translation.text}' has surrounding whitespace.")

    assert not errors, "\n".join(errors[:10]) + (f"\n... and {len(errors) - 10} more errors" if len(errors) > 10 else "")
