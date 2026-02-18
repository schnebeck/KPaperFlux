
import pytest
import xml.etree.ElementTree as ET
from tools.l10n_tool import L10nTool

@pytest.fixture
def ts_file(tmp_path):
    ts_path = tmp_path / "test.ts"
    content = '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE TS><TS version="2.1" language="de"></TS>'
    ts_path.write_text(content, encoding="utf-8")
    return ts_path

def test_shortcut_escaping_not_stripping(ts_file):
    """
    If source has no shortcut (e.g. literal && or no &), 
    any single & in translation should be escaped to &&, not stripped.
    """
    tool = L10nTool(ts_file)
    # Source has '&&' which is a literal &, so has_shortcut is False.
    tool.update_translation("Ctx", "Search && Filter", "Suchen & Filtern")
    
    tool.resolve_shortcuts_for_context("Ctx")
    
    tree = ET.parse(ts_file)
    trans = tree.find(".//message[source='Search && Filter']/translation").text
    assert trans == "Suchen && Filtern"

def test_duplicate_with_comments(ts_file):
    """
    Verify that L10nTool can handle different translations for the same source if they have different comments.
    """
    tool = L10nTool(ts_file)
    tool.update_translation("Ctx", "Search", "&Suchen", comment="action")
    tool.update_translation("Ctx", "Search", "Suchen", comment="tooltip")
    
    # resolve shortcuts
    tool.resolve_shortcuts_for_context("Ctx")
    
    tree = ET.parse(ts_file)
    messages = tree.findall(".//message[source='Search']")
    assert len(messages) == 2
    
    # One should have &Suchen (if resolved? wait, source is Search, no &)
    # Actually, if source is 'Search', it has NO shortcut.
    # So resolve_shortcuts will change '&Suchen' to '&&Suchen'.
    
    for msg in messages:
        if msg.findtext("comment") == "action":
            # Rule: source has no shortcut -> translation should be escaped
            assert msg.find("translation").text == "&&Suchen"
        else:
            assert msg.find("translation").text == "Suchen"

def test_has_shortcut_logic():
    # We can test the internal has_shortcut if we want, but let's test via resolve_shortcuts
    pass
