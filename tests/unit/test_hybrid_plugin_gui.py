from unittest.mock import MagicMock
from plugins.hybrid_assembler.plugin import HybridAssemblerPlugin

def test_hybrid_plugin_initialization():
    """
    Test that the HybridAssemblerPlugin correctly initializes its internal state.
    """
    mock_api = MagicMock()
    plugin = HybridAssemblerPlugin(mock_api)
    
    # Check that the dialog attribute exists
    assert hasattr(plugin, "dialog")
    assert plugin.dialog is None

def test_hybrid_plugin_close_logic():
    """
    Test that the plugin correctly resets the reference when the dialog signals it's closing.
    """
    mock_api = MagicMock()
    plugin = HybridAssemblerPlugin(mock_api)
    
    # Simulate a dialog exists
    mock_dialog = MagicMock()
    plugin.dialog = mock_dialog
    
    # Call the cleanup slot
    plugin._on_dialog_closed()
    
    # Reference should be gone
    assert plugin.dialog is None
