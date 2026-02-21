import pytest
import xml.etree.ElementTree as ET
from pathlib import Path
from tools.l10n_tool import L10nTool, MasterMappingTool

@pytest.fixture
def empty_ts(tmp_path):
    ts_file = tmp_path / "test_strings.ts"
    tool = L10nTool(str(ts_file))
    return tool, ts_file

def test_add_and_update_translation(empty_ts):
    tool, ts_path = empty_ts
    tool.update_translation("TestCtx", "Hello", "Hallo")
    
    # Verify XML structure
    tree = ET.parse(ts_path)
    root = tree.getroot()
    msg = root.find(".//context[name='TestCtx']/message[source='Hello']")
    assert msg is not None
    assert msg.find("translation").text == "Hallo"
    
    # Update existing
    tool.update_translation("TestCtx", "Hello", "Moin")
    tree = ET.parse(ts_path)
    msgs = tree.findall(".//context[name='TestCtx']/message[source='Hello']")
    assert len(msgs) == 1
    assert msgs[0].find("translation").text == "Moin"

def test_duplicate_with_comments(empty_ts):
    """Different translations for the same source with different comments."""
    tool, ts_path = empty_ts
    tool.update_translation("Ctx", "Search", "Suchen...", comment="action")
    tool.update_translation("Ctx", "Search", "Hier suchen", comment="tooltip")
    
    tree = ET.parse(ts_path)
    messages = tree.findall(".//message[source='Search']")
    assert len(messages) == 2
    
    comments = [m.findtext("comment") for m in messages]
    assert "action" in comments
    assert "tooltip" in comments

def test_deduplicate(empty_ts):
    tool, ts_path = empty_ts
    # Manually create duplicates in the file
    content = """<?xml version="1.0" encoding="utf-8"?>
<TS version="2.1" language="de">
<context>
    <name>Ctx</name>
    <message><source>A</source><translation>B</translation></message>
    <message><source>A</source><translation>C</translation></message>
</context>
</TS>"""
    ts_path.write_text(content, encoding="utf-8")
    
    tool.deduplicate()
    
    tree = ET.parse(ts_path)
    msgs = tree.findall(".//context[name='Ctx']/message[source='A']")
    assert len(msgs) == 1
    assert msgs[0].find("translation").text == "C" # Keeps the latest

def test_shortcut_extraction_and_resolution(empty_ts):
    tool, _ = empty_ts
    # Case: Simple assignment
    tool.update_translation("TestCtx", "&File", "Datei")
    tool.resolve_shortcuts_for_context("TestCtx")
    
    tree = tool._get_tree()
    root = tree.getroot()
    trans = root.find(".//context[name='TestCtx']/message[source='&File']/translation").text
    assert trans == "&Datei"

def test_shortcut_collision_avoidance(empty_ts):
    tool, _ = empty_ts
    tool.update_translation("TestCtx", "&Edit", "Editieren")
    tool.update_translation("TestCtx", "&Exit", "Ende")
    tool.resolve_shortcuts_for_context("TestCtx")
    
    tree = tool._get_tree()
    root = tree.getroot()
    t1 = root.find(".//context[name='TestCtx']/message[source='&Edit']/translation").text
    t2 = root.find(".//context[name='TestCtx']/message[source='&Exit']/translation").text
    
    # Both should have a shortcut, but different ones
    assert "&" in t1 and "&" in t2
    char1 = t1[t1.find("&")+1].lower()
    char2 = t2[t2.find("&")+1].lower()
    assert char1 != char2

def test_literal_ampersand_escaping(empty_ts):
    tool, _ = empty_ts
    # Source has NO shortcut mnemonic, but a literal &
    tool.update_translation("TestCtx", "Save & Exit", "Speichern & Beenden")
    tool.resolve_shortcuts_for_context("TestCtx")
    
    tree = tool._get_tree()
    root = tree.getroot()
    trans = root.find(".//context[name='TestCtx']/message[source='Save & Exit']/translation").text
    assert trans == "Speichern && Beenden"

def test_reserved_shortcuts(empty_ts):
    tool, _ = empty_ts
    tool.update_translation("TestCtx", "Settings", "Einstellungen") 
    tool.update_translation("TestCtx", "&Edit", "Eingabe")       
    
    # Preserve 'E' for Settings, 'Edit' must choose something else
    tool.resolve_shortcuts_for_context("TestCtx", reserved={"Settings": "&Einstellungen"})
    
    tree = tool._get_tree()
    root = tree.getroot()
    t_eingabe = root.find(".//context[name='TestCtx']/message[source='&Edit']/translation").text
    assert not t_eingabe.lower().startswith("&e")
    assert "&" in t_eingabe

def test_placeholder_protection(empty_ts):
    tool, _ = empty_ts
    tool.update_translation("TestCtx", "&Recent", "%1 öffnen")
    tool.resolve_shortcuts_for_context("TestCtx")
    
    tree = tool._get_tree()
    root = tree.getroot()
    trans = root.find(".//context[name='TestCtx']/message[source='&Recent']/translation").text
    # Should not break %1
    assert "%&1" not in trans
    assert "&%1" not in trans
    assert trans == "%1 &öffnen"

def test_shortcut_collision_detection_helper(empty_ts):
    """Tests the check_shortcut_collisions helper directly."""
    tool, ts_path = empty_ts
    content = """<?xml version="1.0" encoding="utf-8"?>
<TS version="2.1" language="de">
<context>
    <name>CollCtx</name>
    <message><source>S1</source><translation>&amp;Datei</translation></message>
    <message><source>S2</source><translation>&amp;Dokument</translation></message>
</context>
</TS>"""
    ts_path.write_text(content, encoding="utf-8")
    
    collisions = tool.check_shortcut_collisions()
    assert "CollCtx" in collisions
    assert 'd' in collisions["CollCtx"]
    assert len(collisions["CollCtx"]['d']) == 2

@pytest.fixture
def mock_mapping_file(tmp_path):
    mapping_file = tmp_path / "fill_l10n_mock.py"
    content = """
common = {
    # Menus & Actions
    "&File": "&Datei",
}

contexts = {
    "MainWindow": {
        "Filter Panel": "Filter-Panel",
    },
}
"""
    mapping_file.write_text(content, encoding="utf-8")
    return mapping_file

def test_mapping_tool_common_update(mock_mapping_file):
    mapper = MasterMappingTool(str(mock_mapping_file))
    
    # 1. Update existing
    mapper.update_common("&File", "&Akte")
    content = mock_mapping_file.read_text()
    assert '"&File": "&Akte",' in content
    
    # 2. Add new
    mapper.update_common("&Edit", "&Bearbeiten")
    content = mock_mapping_file.read_text()
    assert '"&Edit": "&Bearbeiten",' in content
    assert '"&File": "&Akte",' in content

def test_mapping_tool_context_update(mock_mapping_file):
    mapper = MasterMappingTool(str(mock_mapping_file))
    
    # 1. Update existing in context
    mapper.update_context_override("MainWindow", "Filter Panel", "Filter-&Bereich")
    content = mock_mapping_file.read_text()
    assert '"Filter Panel": "Filter-&Bereich",' in content
    
    # 2. Add new to existing context
    mapper.update_context_override("MainWindow", "Docs", "Doks")
    content = mock_mapping_file.read_text()
    assert '"Docs": "Doks",' in content

def test_mapping_tool_new_context_creation(mock_mapping_file):
    mapper = MasterMappingTool(str(mock_mapping_file))
    
    # Create entirely new context
    mapper.update_context_override("NewWidget", "Hello", "Hallo")
    content = mock_mapping_file.read_text()
    assert '"NewWidget": {' in content
    assert '"Hello": "Hallo",' in content

@pytest.fixture
def complex_mock_mapping(tmp_path):
    mapping_file = tmp_path / "fill_l10n_complex.py"
    content = """
common = { "A": "B" }

contexts = {
    "Existing": {
        "Src": "Trans",
    }
}

def some_logic():
    res = contexts.get("foo", {})
    return res
"""
    mapping_file.write_text(content, encoding="utf-8")
    return mapping_file

def test_mapping_tool_complex_integrity(complex_mock_mapping):
    mapper = MasterMappingTool(str(complex_mock_mapping))
    
    # Add new context
    mapper.update_context_override("NewCtx", "Hello", "Hallo")
    
    content = complex_mock_mapping.read_text()
    
    # Verify it's inside the contexts dict, not at the end of some_logic
    assert '"NewCtx": {' in content
    # The logic after should still be intact and not corrupted
    assert "def some_logic():" in content
    assert 'res = contexts.get("foo", {})' in content
