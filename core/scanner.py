import os
import tempfile
import datetime
import subprocess
import glob
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from PIL import Image

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
        pass
        
    @abstractmethod
    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = 'Color') -> Optional[str]:
        pass

    @abstractmethod
    def scan_pages(self, device_name: str, dpi: int = 200, color_mode: str = 'Color', 
                   use_adf: bool = False, duplex: bool = False, duplex_mode: str = 'LongEdge',
                   page_format: str = 'A4', progress_callback = None) -> List[str]:
        """
        Scan multiple pages into separate PDF files.
        Returns a list of temporary file paths.
        """
        pass


class MockScanner(ScannerDriver):
    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        return [("mock:1", "Mock", "Scanner V1", "Generic")]
        
    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = 'Color') -> Optional[str]:
        pages = self.scan_pages(device_name, dpi, color_mode, use_adf=False)
        return pages[0] if pages else None

    def scan_pages(self, device_name: str, dpi: int = 200, color_mode: str = 'Color', 
                   use_adf: bool = False, duplex: bool = False, duplex_mode: str = 'LongEdge',
                   progress_callback = None) -> List[str]:
        if not use_adf:
            return ["/tmp/mock_scan.pdf"]
        return ["/tmp/mock_p1.pdf", "/tmp/mock_p2.pdf"]


class SaneScanner(ScannerDriver):
    def __init__(self):
        if SANE_AVAILABLE:
            try:
                sane.init()
            except Exception as e:
                print(f"SANE init failed: {e}")
                
    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        if not SANE_AVAILABLE:
            return []
        try:
            # SANE discovery can be flaky; re-init sometimes helps find devices that just went online
            try: sane.init()
            except: pass
            devices = sane.get_devices()
            print(f"[DEBUG] SANE discovered {len(devices)} devices: {devices}")
            return devices
        except Exception as e:
            print(f"SANE list_devices error: {e}")
            return []
            
    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = 'Color') -> Optional[str]:
        pages = self.scan_pages(device_name, dpi, color_mode, use_adf=False, duplex=False)
        return pages[0] if pages else None

    def _discover_capabilities(self, device_name, use_adf, duplex):
        """Helper to find correct source name and duplex options via SANE discovery."""
        discovered_source = "Flatbed"
        has_duplex_opt = False
        if not SANE_AVAILABLE: 
            return "ADF" if use_adf else "Flatbed", False

        try:
            dev = sane.open(device_name)
            opts = {opt[1]: opt for opt in dev.get_options()}
            
            if 'source' in opts:
                # opt[8] is the list of permitted values for a constraint
                try: available = opts['source'][8]
                except: available = []
                print(f"DEBUG: Available sources for {device_name}: {available}")
                
                if use_adf:
                    found = False
                    if duplex:
                        # Try to find a duplex-specific source FIRST
                        for p in ["ADF Duplex", "Automatic Document Feeder Duplex", "Duplex"]:
                            if p in available:
                                discovered_source = p
                                found = True
                                break
                    
                    if not found:
                        # Fallback to standard ADF sources
                        prio = ["ADF", "Automatic Document Feeder", "Automatic Document Feeder(centered)"]
                        for p in prio:
                            if p in available:
                                discovered_source = p
                                break
                else:
                    for p in ["Flatbed", "Stationary"]:
                        if p in available:
                            discovered_source = p
                            break
            else:
                discovered_source = "ADF" if use_adf else "Flatbed"
            
            if duplex and 'duplex' in opts:
                has_duplex_opt = True
                
            dev.close()
        except Exception as e:
            print(f"DEBUG: Capability discovery failed: {e}")
            discovered_source = "ADF" if use_adf else "Flatbed"
            
        return discovered_source, has_duplex_opt

    def scan_pages(self, device_name: str, dpi: int = 200, color_mode: str = 'Color', 
                   use_adf: bool = False, duplex: bool = False, duplex_mode: str = 'LongEdge',
                   page_format: str = 'A4', progress_callback = None) -> List[str]:
        
        # 1. Discover the correct source name and duplex options
        source_name, has_duplex_opt = self._discover_capabilities(device_name, use_adf, duplex)
        print(f"DEBUG: Using source '{source_name}' (duplex_opt: {has_duplex_opt})")

        # 2. Geometry / Page Size
        # A4: 210 x 297 mm
        # Letter: 215.9 x 279.4 mm
        # Legal: 215.9 x 355.6 mm
        # Default/Max: don't set
        geom_args = []
        if page_format == 'A4':
            geom_args = ['-x', '210', '-y', '297']
        elif page_format == 'Letter':
            geom_args = ['-x', '215.9', '-y', '279.4']
        elif page_format == 'Legal':
            geom_args = ['-x', '215.9', '-y', '355.6']

        # 3. STRATEGY: For ADF/Duplex, 'scanimage --batch' is much more reliable
        if use_adf:
            extra_args = list(geom_args)
            if duplex and has_duplex_opt:
                extra_args.append('--duplex=yes')
            
            try:
                results = self._scan_via_scanimage(device_name, dpi, color_mode, source_name, extra_args, progress_callback)
                if results:
                    return results
            except Exception as e:
                print(f"SANE: scanimage batch failed ({e}), falling back to python-sane loop...")

        # FALLBACK: python-sane loop
        return self._scan_via_python_sane(device_name, dpi, color_mode, use_adf, duplex, duplex_mode, progress_callback)

    def _scan_via_scanimage(self, device, dpi, mode, source, extra_args, progress_callback) -> List[str]:
        temp_dir = tempfile.mkdtemp(prefix="kpaper_scan_")
        pattern = os.path.join(temp_dir, "p%d.tif")
        
        # Adjust mode name (some drivers use lowercase)
        mode_val = mode
        if "brother" in device.lower() or "escl" in device.lower():
            # Usually Color or Gray is fine, but sometimes brother-specific ones like 'True Gray'
            pass

        cmd = [
            'scanimage', 
            '-d', device,
            '--source', source,
            '--resolution', str(dpi),
            '--mode', mode_val,
            '--batch=' + pattern,
            '--batch-prompt=no',
            '--format=tiff'
        ] + extra_args
        
        print(f"DEBUG: Running {' '.join(cmd)}")
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            while process.poll() is None:
                if progress_callback:
                    count = len(glob.glob(os.path.join(temp_dir, "*.tif")))
                    if count > 0:
                        progress_callback(count, -1)
                process.wait(timeout=1.0)
        except Exception as e:
            print(f"ERROR calling scanimage: {e}")
            return []

        results = []
        tif_files = sorted(glob.glob(os.path.join(temp_dir, "*.tif")), key=lambda x: int(os.path.basename(x)[1:-4]))
        
        for i, tif in enumerate(tif_files):
            try:
                pdf_path = os.path.join(temp_dir, f"scan_p{i+1}.pdf")
                with Image.open(tif) as im:
                    im.save(pdf_path, "PDF", resolution=dpi)
                results.append(pdf_path)
            except Exception as e:
                print(f"ERROR converting {tif} to PDF: {e}")
            finally:
                try: os.remove(tif)
                except: pass

        print(f"SANE: scanimage batch finished. Found {len(results)} pages.")
        return results

    def _scan_via_python_sane(self, device_name, dpi, color_mode, use_adf, duplex, duplex_mode, progress_callback):
        if not SANE_AVAILABLE:
            raise RuntimeError("python-sane not installed.")
            
        results = []
        dev = None
        try:
            dev = sane.open(device_name)
            options = {opt[1]: opt for opt in dev.get_options()}
            
            if 'resolution' in options:
                try: dev.resolution = dpi
                except: pass
            if 'mode' in options:
                try: dev.mode = color_mode
                except: pass

            if 'source' in options:
                source_name, _ = self._discover_capabilities(device_name, use_adf, duplex)
                try: dev.source = source_name
                except: pass
            
            if duplex and 'duplex' in options:
                try: dev.duplex = True
                except: pass

            page_idx = 0
            while True:
                page_idx += 1
                if progress_callback:
                    progress_callback(page_idx, -1)
                try:
                    dev.start()
                    im = dev.snap()
                    fd, path = tempfile.mkstemp(suffix=".pdf", prefix=f"scan_p{page_idx}_")
                    os.close(fd)
                    im.save(path, "PDF", resolution=dpi)
                    results.append(path)
                    if not use_adf: break 
                except Exception as e:
                    print(f"SANE loop break: {e}")
                    break
            return results
        except Exception as e:
            print(f"SANE python-sane error: {e}")
            raise
        finally:
            if dev: dev.close()
    
    def cleanup(self):
        if SANE_AVAILABLE:
            try: sane.exit()
            except: pass

def get_scanner_driver(driver_type: str = "auto") -> ScannerDriver:
    if driver_type == "mock": return MockScanner()
    elif driver_type == "sane": return SaneScanner()
    else:
        if SANE_AVAILABLE: return SaneScanner()
        else: return MockScanner()
