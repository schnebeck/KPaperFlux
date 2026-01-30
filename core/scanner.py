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
    def get_source_list(self, device_name: str) -> List[str]:
        """Return list of supported sources (Flatbed, ADF, etc.)"""
        pass

    @abstractmethod
    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = 'Color') -> Optional[str]:
        pass

    @abstractmethod
    def scan_pages(self, device_name: str, dpi: int = 200, color_mode: str = 'Color', 
                   source: str = 'Flatbed', duplex_mode: str = 'LongEdge',
                   page_format: str = 'A4', progress_callback = None) -> List[str]:
        """
        Scan multiple pages into separate PDF files.
        Returns a list of temporary file paths.
        """
        pass


class MockScanner(ScannerDriver):
    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        return [("mock:1", "Mock", "Scanner V1", "Generic")]
        
    def get_source_list(self, device_name: str) -> List[str]:
        return ["Flatbed", "ADF", "ADF Duplex"]
        
    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = 'Color') -> Optional[str]:
        pages = self.scan_pages(device_name, dpi, color_mode, source="Flatbed")
        return pages[0] if pages else None

    def scan_pages(self, device_name: str, dpi: int = 200, color_mode: str = 'Color', 
                   source: str = 'Flatbed', duplex_mode: str = 'LongEdge',
                   page_format: str = 'A4', progress_callback = None) -> List[str]:
        if "ADF" not in source:
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
            
    def get_source_list(self, device_name: str) -> List[str]:
        if not SANE_AVAILABLE: return ["Flatbed"]
        try:
            dev = sane.open(device_name)
            opts = {opt[1]: opt for opt in dev.get_options()}
            sources = []
            if 'source' in opts:
                try: sources = opts['source'][8]
                except: sources = ["Flatbed"]
            dev.close()
            return sources
        except:
            return ["Flatbed", "ADF"]

    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = 'Color') -> Optional[str]:
        pages = self.scan_pages(device_name, dpi, color_mode, source="Flatbed")
        return pages[0] if pages else None

    def scan_pages(self, device_name: str, dpi: int = 200, color_mode: str = 'Color', 
                   source: str = 'Flatbed', duplex_mode: str = 'LongEdge',
                   page_format: str = 'A4', progress_callback = None) -> List[str]:
        
        # 1. Automatic Duplex Flag
        is_adf = any(kw in source for kw in ["ADF", "Feeder", "Einzug"])
        is_duplex = any(kw in source for kw in ["Duplex", "Beidseitig", "Zweiseitig"])
        
        has_duplex_opt = False
        if SANE_AVAILABLE:
            try:
                dev = sane.open(device_name)
                opts = {opt[1]: opt for opt in dev.get_options()}
                if 'duplex' in opts: has_duplex_opt = True
                dev.close()
            except: pass

        # 2. Geometry / Page Size
        geom_args = []
        if page_format == 'A4':
            geom_args = ['-x', '210mm', '-y', '296mm']
        elif page_format == 'Letter':
            geom_args = ['-x', '215.9mm', '-y', '279.4mm']
        elif page_format == 'Legal':
            geom_args = ['-x', '215.9mm', '-y', '355.6mm']

        # 3. STRATEGY: For ADF/Duplex, 'scanimage --batch' is much more reliable
        if is_adf:
            extra_args = list(geom_args)
            if is_duplex and has_duplex_opt:
                extra_args.append('--duplex=yes')
            
            try:
                results = self._scan_via_scanimage(device_name, dpi, color_mode, source, extra_args, progress_callback)
                if results:
                    return results
            except Exception as e:
                print(f"SANE: scanimage batch failed ({e}), falling back to python-sane loop...")

        # FALLBACK: python-sane loop
        return self._scan_via_python_sane(device_name, dpi, color_mode, is_adf, is_duplex, source, duplex_mode, progress_callback)

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
                try:
                    # Wait a bit, if it times out, just loop again to check progress
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    continue
        except Exception as e:
            print(f"ERROR calling scanimage: {e}")
            return []

        results = []
        tif_files = sorted(glob.glob(os.path.join(temp_dir, "*.tif")), key=lambda x: int(os.path.basename(x)[1:-4]))
        
        for i, tif in enumerate(tif_files):
            try:
                pdf_path = os.path.join(temp_dir, f"scan_p{i+1}.pdf")
                with Image.open(tif) as im:
                    # PIXEL-LEVEL A4 NORMALIZER (User Algorithm)
                    if page_format == 'A4':
                        print(f"\n--- A4 NORMALIZER DEBUG (User Algorithm) ---")
                        target_w_mm, target_h_mm = 210.0, 297.0
                        
                        # Get reliable DPI
                        info_dpi = im.info.get('dpi')
                        res_unit = im.info.get('resolution_unit', 2) # 2: inch, 3: cm
                        
                        if info_dpi and info_dpi[0] > 0:
                            cur_dpi_orig = float(info_dpi[0])
                        else:
                            cur_dpi_orig = float(dpi)
                        
                        # Normalize DPI to Dots Per Inch (DPI)
                        if res_unit == 3: # Centimeters
                            cur_dpi = cur_dpi_orig * 2.54
                            print(f"DEBUG: Resolution unit is CM. Converting {cur_dpi_orig} dpc to {cur_dpi:.1f} dpi")
                        else:
                            cur_dpi = cur_dpi_orig
                        
                        # Calculate target pixel dimensions for A4 at this resolution
                        target_w_px = int(round((target_w_mm / 25.4) * cur_dpi))
                        target_h_px = int(round((target_h_mm / 25.4) * cur_dpi))
                        
                        phys_w_mm = (im.width / cur_dpi) * 25.4
                        phys_h_mm = (im.height / cur_dpi) * 25.4
                        
                        print(f"1. Input: {im.width}x{im.height} px ({phys_w_mm:.1f}x{phys_h_mm:.1f}mm) at {cur_dpi:.1f} DPI")
                        print(f"2. Target A4: {target_w_px}x{target_h_px} px ({target_w_mm}x{target_h_mm}mm)")
                        
                        # Calculate scaling factor based on width (shorter side)
                        scale_factor = target_w_px / im.width
                        scaled_h = int(round(im.height * scale_factor))
                        
                        print(f"3. Scaling: Factor {scale_factor:.4f} (Result: {target_w_px}x{scaled_h} px)")
                        
                        im = im.resize((target_w_px, scaled_h), Image.Resampling.LANCZOS)
                        
                        # Crop the vertical excess
                        if im.height > target_h_px:
                            excess = im.height - target_h_px
                            print(f"4. [CROP] Height {im.height} > {target_h_px}. Removing bottom {excess} px.")
                            im = im.crop((0, 0, target_w_px, target_h_px))
                        else:
                            print(f"4. [SKIP CROP] Height {im.height} is already <= {target_h_px}.")
                        
                        save_resolution = float(cur_dpi)
                        print(f"5. Final: {im.width}x{im.height} px. Saving PDF at {save_resolution:.1f} DPI.\n")
                    else:
                        save_resolution = float(im.info.get('dpi', (dpi, dpi))[0])
                    
                    if im.mode != "RGB":
                        im = im.convert("RGB")
                    
                    im.save(pdf_path, "PDF", resolution=save_resolution)
                results.append(pdf_path)
            except Exception as e:
                print(f"ERROR converting {tif} to PDF: {e}")
            finally:
                try: os.remove(tif)
                except: pass

        print(f"SANE: scanimage batch finished. Found {len(results)} pages.")
        return results

    def _scan_via_python_sane(self, device_name, dpi, color_mode, is_adf, is_duplex, source, duplex_mode, progress_callback):
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
                # Use exactly the source selected by the user
                try: dev.source = source
                except: pass
            
            if is_duplex and 'duplex' in options:
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
                    if not is_adf: break 
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
