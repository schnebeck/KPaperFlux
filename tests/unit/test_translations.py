
import os
import xml.etree.ElementTree as ET
import pytest
from PyQt6.QtCore import QTranslator, QCoreApplication

# Paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
TS_FILE_PATH = os.path.join(PROJECT_ROOT, 'resources', 'translations', 'kpaperflux_de.ts')
QM_FILE_PATH = os.path.join(PROJECT_ROOT, 'resources', 'translations', 'kpaperflux_de.qm')

def test_ts_file_exists():
    """Verify that the translation source (.ts) file exists."""
    assert os.path.exists(TS_FILE_PATH), f"Translation file not found at {TS_FILE_PATH}"

def test_qm_file_exists():
    """Verify that the compiled translation (.qm) file exists."""
    assert os.path.exists(QM_FILE_PATH), r"Compiled translation file not found. Did you run lrelease?"

def test_source_format_integrity():
    """
    Parses the .ts file and ensures source strings are formatted correctly:
    - No leading/trailing spaces in <source> content.
    - No split accelerators like '& File' (should be '&File').
    """
    tree = ET.parse(TS_FILE_PATH)
    root = tree.getroot()
    
    # Iterate over all contexts and messages
    for context in root.findall('context'):
        context_name = context.find('name').text
        for message in context.findall('message'):
            source_node = message.find('source')
            if source_node is None or source_node.text is None:
                continue
                
            source_text = source_node.text
            
            # Check 1: No leading/trailing whitespace
            assert source_text == source_text.strip(), \
                f"Context '{context_name}': Source text '{source_text}' has leading/trailing whitespace."
            
            # Check 2: Accelerator format '& ' (bad) vs '&' (good)
            # We want to forbid "& " followed by a letter, unless it's a literal sentence.
            # But for menu items it's critical.
            if "& " in source_text:
                # Warning or Error? Given the recent bug, we treat it as Error for menu items.
                # Heuristic: if text is short (< 30 chars) and contains "& ", it's likely a broken accelerator.
                if len(source_text) < 30:
                     pytest.fail(f"Context '{context_name}': Suspicious broken accelerator in '{source_text}'. Should likely be '&Word' not '& Word'.")

def test_all_items_translated():
    """
    Parses the .ts file and ensures every source has a translation.
    """
    tree = ET.parse(TS_FILE_PATH)
    root = tree.getroot()
    
    unfinished_count = 0
    empty_translation_count = 0
    
    for context in root.findall('context'):
        context_name = context.find('name').text
        for message in context.findall('message'):
            source_text = message.find('source').text
            translation_node = message.find('translation')
            
            # content of translation
            trans_text = translation_node.text if translation_node is not None else ""
            
            # specific attribute "type" might be "unfinished" (Qt Linguist)
            is_unfinished = translation_node.get('type') == 'unfinished'
            
            if is_unfinished:
                unfinished_count += 1
                print(f"Unfinished: [{context_name}] {source_text} -> {trans_text}")
                
            if not trans_text:
                empty_translation_count += 1
                
    # Assertions
    # We insist on 0 empty translations for a "shippable" state
    assert empty_translation_count == 0, f"Found {empty_translation_count} empty translations."
    
    # We might warn about unfinished, or fail. 
    # For this verification task, we want to fail if any exist to prove "all words translated".
    assert unfinished_count == 0, f"Found {unfinished_count} unfinished translations."

def test_translation_loading_qt():
    """
    Integration test: Load the QM file into QTranslator and verify key strings.
    """
    # Needs a QCoreApplication instance
    app = QCoreApplication.instance()
    if not app:
        app = QCoreApplication([])
    
    translator = QTranslator()
    loaded = translator.load(QM_FILE_PATH)
    assert loaded, "Failed to load .qm file with QTranslator"
    
    # Test specific keys that were broken
    # Context: MainWindow, Source: &File -> Target: &Datei
    
    # Note: QTranslator.translate(context, source)
    
    # 1. &File
    result_file = translator.translate("MainWindow", "&File")
    assert result_file == "&Datei", f"Translation mismatch for '&File'. Got '{result_file}'"
    
    # 2. &View
    result_view = translator.translate("MainWindow", "&View")
    assert result_view == "&Ansicht", f"Translation mismatch for '&View'. Got '{result_view}'"
    
    # 3. &Config
    result_config = translator.translate("MainWindow", "&Config")
    assert result_config == "&Konfiguration", f"Translation mismatch for '&Config'. Got '{result_config}'"

    # 4. &Help
    result_help = translator.translate("MainWindow", "&Help")
    assert result_help == "&Hilfe", f"Translation mismatch for '&Help'. Got '{result_help}'"

