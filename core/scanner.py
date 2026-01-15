
import os
import tempfile
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from pathlib import Path

# Try importing sane, but don't fail if missing (development environment)
try:
    import sane
    SANE_AVAILABLE = True
except ImportError:
    SANE_AVAILABLE = False


class ScannerDriver(ABC):
    """
    Abstract interface for scanner devices.
    """
    
    @abstractmethod
    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        """
        List available devices.
        Returns list of tuples: (device_name, vendor, model, type)
        """
        pass
        
    @abstractmethod
    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = 'Color') -> Optional[str]:
        """
        Scan a single page.
        Returns the path to the temporary image/PDF file.
        :param device_name: Device identifier
        :param dpi: Resolution
        :param color_mode: 'Color', 'Gray', 'Lineart'
        """
        pass


class MockScanner(ScannerDriver):
    """
    Simulates a scanner for testing/development.
    Generates a valid dummy PDF file.
    """
    
    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        return [
            ("mock:001", "Virtual", "MockScanner 3000", "virtual"),
            ("mock:002", "Virtual", "Debug Scanner X", "virtual")
        ]
        
    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = 'Color') -> Optional[str]:
        print(f"MockScanner: Scanning from {device_name} at {dpi}dpi ({color_mode})...")
        
        # Create a valid minimal PDF using pikepdf
        import pikepdf
        
        fd, path = tempfile.mkstemp(suffix=".pdf", prefix="scan_")
        os.close(fd)
        
        try:
            pdf = pikepdf.new()
            pdf.add_blank_page(page_size=(595, 842)) # A4 approx
            pdf.save(path)
            # In a real mock, we might want to put text/image on it, 
            # but for architecture testing, a blank PDF is a valid "File".
            print(f"MockScanner: Produced {path}")
            return path
        except Exception as e:
            print(f"MockScanner Error: {e}")
            if os.path.exists(path):
                os.remove(path)
            return None


class SaneScanner(ScannerDriver):
    """
    Wrapper around python-sane to drive real hardware.
    """
    
    def __init__(self):
        if not SANE_AVAILABLE:
            print("Warning: python-sane not installed. usage will fail.")
        else:
            try:
                sane.init()
            except Exception as e:
                print(f"SANE Init failed: {e}")
    
    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        if not SANE_AVAILABLE:
            return []
        try:
            # sane.get_devices() returns list of (name, vendor, model, type)
            return sane.get_devices()
        except Exception as e:
            print(f"SANE list_devices error: {e}")
            return []
            
    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = 'Color') -> Optional[str]:
        if not SANE_AVAILABLE:
            print("SANE not available.")
            return None
            
        try:
            dev = sane.open(device_name)
            
            # Set options
            # Note: Option names vary by backend. This is a best-effort standard setting.
            try:
                dev.resolution = dpi
            except:
                pass
                
            try:
                dev.mode = color_mode # 'Color', 'Gray', 'Lineart'
            except:
                pass
                
            dev.start()
            im = dev.snap()
            
            # Save to temp file
            # SANE returns a PIL Image
            fd, path = tempfile.mkstemp(suffix=".pdf", prefix="scan_")
            os.close(fd)
            
            # Save as PDF directly via Pillow
            im.save(path, "PDF", resolution=dpi)
            
            dev.close()
            return path
            
        except Exception as e:
            print(f"SANE scan error: {e}")
            return None
    
    def cleanup(self):
        if SANE_AVAILABLE:
            sane.exit()

def get_scanner_driver(driver_type: str = "auto") -> ScannerDriver:
    """
    Factory to get the appropriate driver.
    """
    if driver_type == "mock":
        return MockScanner()
    elif driver_type == "sane":
        return SaneScanner()
    else:
        # Auto: Try SANE, if available and has devices. Else Mock?
        # For now, if SANE is importable, use it. If not, use Mock?
        # User defined spec: "Unterstützung für den Scanner". 
        # Safest is: return Sane if available, else Mock.
        if SANE_AVAILABLE:
            return SaneScanner()
        else:
            return MockScanner()
