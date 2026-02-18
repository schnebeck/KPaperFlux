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
