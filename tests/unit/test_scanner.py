
import os
import pytest
import pikepdf
from core.scanner import MockScanner, get_scanner_driver, ScannerDriver

def test_mock_scanner_devices():
    scanner = MockScanner()
    devices = scanner.list_devices()
    assert len(devices) > 0
    assert devices[0][0] == "mock:001"

def test_mock_scanner_scan():
    scanner = MockScanner()
    # device_name ignored by mock
    output_path = scanner.scan_page("mock:001", dpi=150, color_mode="Gray")
    
    assert output_path is not None
    assert os.path.exists(output_path)
    assert output_path.endswith(".pdf")
    
    # Verify it is a valid PDF
    with pikepdf.Pdf.open(output_path) as pdf:
        assert len(pdf.pages) == 1
    
    # Cleanup
    os.remove(output_path)

def test_factory_returns_driver():
    # Force mock
    driver = get_scanner_driver("mock")
    assert isinstance(driver, MockScanner)
    
    # Auto
    driver_auto = get_scanner_driver("auto")
    assert isinstance(driver_auto, ScannerDriver)
