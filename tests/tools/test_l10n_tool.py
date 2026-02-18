import os
import pytest
import xml.etree.ElementTree as ET
from tools.l10n_tool import L10nTool

@pytest.fixture
def empty_ts(tmp_path):
    ts_path = tmp_path / "test.ts"
    content = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="de">
<context>
    <name>TestContext</name>
</context>
</TS>"""
    ts_path.write_text(content, encoding="utf-8")
    return ts_path

def test_add_translation(empty_ts):
    tool = L10nTool(empty_ts)
    tool.update_translation("TestContext", "Hello", "Hallo")
    
    # Verify XML
    tree = ET.parse(empty_ts)
    root = tree.getroot()
    context = root.find("context[name='TestContext']")
    assert context is not None
    
    msg = context.find("message[source='Hello']")
    assert msg is not None
    assert msg.find("translation").text == "Hallo"

def test_update_existing_translation(empty_ts):
    tool = L10nTool(empty_ts)
    tool.update_translation("TestContext", "Hello", "Hallo")
    tool.update_translation("TestContext", "Hello", "Moin")
    
    tree = ET.parse(empty_ts)
    msgs = tree.findall(".//context[name='TestContext']/message[source='Hello']")
    assert len(msgs) == 1
    assert msgs[0].find("translation").text == "Moin"

def test_deduplicate(tmp_path):
    ts_path = tmp_path / "dup.ts"
    content = """<?xml version="1.0" encoding="utf-8"?>
<TS version="2.1" language="de">
<context>
    <name>Ctx</name>
    <message><source>A</source><translation>B</translation></message>
    <message><source>A</source><translation>C</translation></message>
</context>
</TS>"""
    ts_path.write_text(content, encoding="utf-8")
    
    tool = L10nTool(ts_path)
    tool.deduplicate()
    
    tree = ET.parse(ts_path)
    msgs = tree.findall(".//context[name='Ctx']/message[source='A']")
    assert len(msgs) == 1
    # Should keep the last or first? Let's say last (latest update)
    assert msgs[0].find("translation").text == "C"
def test_shortcut_collision_detection(tmp_path):
    ts_path = tmp_path / "shortcuts.ts"
    content = """<?xml version="1.0" encoding="utf-8"?>
<TS version="2.1" language="de">
<context>
    <name>CollCtx</name>
    <message><source>S1</source><translation>&amp;Datei</translation></message>
    <message><source>S2</source><translation>&amp;Dokument</translation></message>
    <message><source>S3</source><translation>Werk&amp;zeuge</translation></message>
    <message><source>S4</source><translation>Me&amp;nü</translation></message>
    <message><source>S5</source><translation>G&amp;amp;&amp;amp;H</translation></message> <!-- Escaped, no collision with &H if we had one -->
</context>
</TS>"""
    ts_path.write_text(content, encoding="utf-8")
    
    tool = L10nTool(ts_path)
    collisions = tool.check_shortcut_collisions()
    
    assert "CollCtx" in collisions
    # Collision on 'd' (Datei and Dokument)
    assert 'd' in collisions["CollCtx"]
    assert len(collisions["CollCtx"]['d']) == 2
    # No collision on 'z' (Werkzeuge)
    assert 'z' not in collisions["CollCtx"]
    # No collision on escaped 'G&&H'
    assert 'g' not in collisions["CollCtx"]
