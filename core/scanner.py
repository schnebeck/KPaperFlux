
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


    @abstractmethod
    def scan_pages(self, device_name: str, dpi: int = 200, color_mode: str = 'Color', 
                   use_adf: bool = False, duplex: bool = False, progress_callback = None) -> List[str]:
        """
        Scan multiple pages (ADF).
        Returns list of temporary file paths.
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
        pages = self.scan_pages(device_name, dpi, color_mode, use_adf=False)
        return pages[0] if pages else None

    def scan_pages(self, device_name: str, dpi: int = 200, color_mode: str = 'Color', 
                   use_adf: bool = False, duplex: bool = False, progress_callback = None) -> List[str]:
        print(f"MockScanner: Scanning from {device_name}...")
        
        count = 3 if use_adf else 1
        if duplex and use_adf:
            count *= 2
            
        results = []
        import pikepdf
        
        for i in range(count):
            if progress_callback:
                progress_callback(i + 1, count)
                
            fd, path = tempfile.mkstemp(suffix=".pdf", prefix=f"scan_p{i+1}_")
            os.close(fd)
            
            pdf = pikepdf.new()
            pdf.add_blank_page(page_size=(595, 842))
            pdf.save(path)
            results.append(path)
            
        return results


class SaneScanner(ScannerDriver):
    """
    Wrapper around python-sane to drive real hardware.
    Includes logic for ADF and Duplex discovery.
    """
    
    def __init__(self):
        if not SANE_AVAILABLE:
            print("Warning: python-sane not installed.")
        else:
            try:
                sane.init()
            except Exception as e:
                print(f"SANE Init failed: {e}")
    
    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        if not SANE_AVAILABLE:
            return []
        try:
            return sane.get_devices()
        except Exception as e:
            print(f"SANE list_devices error: {e}")
            return []
            
    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = 'Color') -> Optional[str]:
        pages = self.scan_pages(device_name, dpi, color_mode, use_adf=False)
        return pages[0] if pages else None

    def scan_pages(self, device_name: str, dpi: int = 200, color_mode: str = 'Color', 
                   use_adf: bool = False, duplex: bool = False, progress_callback = None) -> List[str]:
        if not SANE_AVAILABLE:
            raise RuntimeError("python-sane not installed.")
            
        results = []
        dev = None
        try:
            dev = sane.open(device_name)
            
            # --- Option Discovery & Setting ---
            params = dev.get_parameters()
            options = {opt[1]: opt for opt in dev.get_options()}
            
            # 1. Resolution
            if 'resolution' in options:
                try: dev.resolution = dpi
                except: pass
                
            # 2. Mode (Color/Gray)
            if 'mode' in options:
                try: dev.mode = color_mode
                except: pass

            # 3. Source (ADF vs Flatbed)
            if use_adf and 'source' in options:
                src_opt = options['source']
                # Try to find ADF in available values
                # src_opt[8] is often the list of strings for constrained options
                # But python-sane varies. dev.opt['source'].constraint works sometimes.
                # Usually we just try to set it.
                adf_names = ["ADF", "Automatic Document Feeder", "ADF Duplex"]
                for name in adf_names:
                    try:
                        dev.source = name
                        print(f"SANE: Set source to {name}")
                        break
                    except:
                        continue

            # 4. Duplex (Specific to backend)
            if duplex:
                if 'duplex' in options:
                    try: dev.duplex = True
                    except: pass
                elif 'source' in options:
                    # Some eSCL scanners use Source="ADF Duplex"
                    try: dev.source = "ADF Duplex"
                    except: pass

            # --- Scanning Loop ---
            page_idx = 0
            while True:
                page_idx += 1
                if progress_callback:
                    progress_callback(page_idx, -1) # -1 means "unknown total"
                
                try:
                    dev.start()
                    im = dev.snap()
                    
                    fd, path = tempfile.mkstemp(suffix=".pdf", prefix=f"scan_p{page_idx}_")
                    os.close(fd)
                    im.save(path, "PDF", resolution=dpi)
                    results.append(path)
                    
                    if not use_adf:
                        break # Only one page for flatbed
                except Exception as e:
                    # In python-sane, an exception often signals Out of Paper
                    print(f"SANE loop break: {e}")
                    break
                    
            return results
            
        except Exception as e:
            print(f"SANE scan error: {e}")
            raise
        finally:
            if dev:
                dev.close()
    
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
