from unittest.mock import MagicMock, patch
from gui.main_window import MainWindow
from plugins.hybrid_assembler.plugin import HybridAssemblerPlugin
from core.plugins.base import ApiContext

def test_hybrid_plugin_initialization():
    """
    Test that the HybridAssemblerPlugin correctly initializes its internal state.
    This prevents the AttributeError: '_matching_dialog'
    """
    mock_api = MagicMock()
    plugin = HybridAssemblerPlugin(mock_api)
    
    # Check that THE critical attribute exists right after init
    assert hasattr(plugin, "_matching_dialog")
    assert plugin._matching_dialog is None

def test_hybrid_plugin_open_dialog_logic(qapp, qtbot):
    """
    Test the logic of opening the dialog (handling singleton instance).
    """
    mock_api = MagicMock()
    mock_api.main_window = MagicMock()
    plugin = HybridAssemblerPlugin(mock_api)
    
    # Use patch to prevent actual Dialog creation and show()
    with patch('plugins.hybrid_assembler.matching_dialog.MatchingDialog') as MockDialog:
        # First call: creates new dialog
        plugin.open_matching_dialog()
        
        assert MockDialog.called
        assert plugin._matching_dialog is not None
        
        # Capture the first instance
        first_instance = plugin._matching_dialog
        
        # Second call: should NOT create a new one, but raise/activate existing
        MockDialog.reset_mock()
        plugin.open_matching_dialog()
        
        assert not MockDialog.called
        assert plugin._matching_dialog is first_instance
        first_instance.activateWindow.assert_called()

def test_hybrid_plugin_close_logic():
    """
    Test that the plugin correctly resets the reference when the dialog signals it's closing.
    """
    mock_api = MagicMock()
    plugin = HybridAssemblerPlugin(mock_api)
    
    # Simulate a dialog exists
    mock_dialog = MagicMock()
    plugin._matching_dialog = mock_dialog
    
    # Call the cleanup slot
    plugin._on_dialog_closed()
    
    # Reference should be gone
    assert plugin._matching_dialog is None
