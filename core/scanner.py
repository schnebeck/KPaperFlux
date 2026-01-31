"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/scanner.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Drivers and interfaces for scanner interaction. Supports SANE-based
                hardware scanning and mock drivers for development/testing.
------------------------------------------------------------------------------
"""

import datetime
import glob
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

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
        """
        Lists available scanner devices.

        Returns:
            A list of tuples containing (name, vendor, model, type).
        """
        pass
        
    @abstractmethod
    def get_source_list(self, device_name: str) -> List[str]:
        """
        Returns a list of supported sources (e.g., Flatbed, ADF).

        Args:
            device_name: The name/ID of the scanner device.

        Returns:
            A list of supported source strings.
        """
        pass

    @abstractmethod
    def get_resolution_list(self, device_name: str) -> List[int]:
        """
        Returns a list of supported resolutions (DPI).

        Args:
            device_name: The name/ID of the scanner device.

        Returns:
            A list of supported resolutions in DPI.
        """
        pass

    @abstractmethod
    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = "Color") -> Optional[str]:
        """
        Scans a single page.

        Args:
            device_name: The name/ID of the scanner device.
            dpi: Resolution in dots per inch.
            color_mode: The color mode (e.g., 'Color', 'Gray', 'Lineart').

        Returns:
            The path to the scanned page (temporary file), or None if failed.
        """
        pass

    @abstractmethod
    def scan_pages(
        self,
        device_name: str,
        dpi: int = 200,
        color_mode: str = "Color",
        source: str = "Flatbed",
        duplex_mode: str = "LongEdge",
        page_format: str = "A4",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[str]:
        """
        Scans multiple pages.

        Args:
            device_name: The name/ID of the scanner device.
            dpi: Resolution in dots per inch.
            color_mode: The color mode.
            source: The paper source (e.g., 'Flatbed', 'ADF').
            duplex_mode: Duplex configuration.
            page_format: Paper format (e.g., 'A4').
            progress_callback: Optional function for progress reporting (current_page, total).

        Returns:
            A list of temporary file paths for the scanned pages.
        """
        pass


class MockScanner(ScannerDriver):
    """
    Mock implementation of a scanner driver for testing and development.
    """

    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        """
        Lists mock devices.

        Returns:
            A list of mock device tuples.
        """
        return [("mock:1", "Mock", "Scanner V1", "Generic")]

    def get_source_list(self, device_name: str) -> List[str]:
        """
        Returns mock source list.

        Args:
            device_name: Device name (ignored).

        Returns:
            List of supported sources.
        """
        return ["Flatbed", "ADF", "ADF Duplex"]

    def get_resolution_list(self, device_name: str) -> List[int]:
        """
        Returns mock resolution list.

        Args:
            device_name: Device name (ignored).

        Returns:
            List of supported resolutions.
        """
        return [75, 150, 200, 300, 600]

    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = "Color") -> Optional[str]:
        """
        Simulates a single page scan.

        Args:
            device_name: Device name.
            dpi: Resolution.
            color_mode: Color mode.

        Returns:
            Path to the mock page.
        """
        pages = self.scan_pages(device_name, dpi, color_mode, source="Flatbed")
        return pages[0] if pages else None

    def scan_pages(
        self,
        device_name: str,
        dpi: int = 200,
        color_mode: str = "Color",
        source: str = "Flatbed",
        duplex_mode: str = "LongEdge",
        page_format: str = "A4",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[str]:
        """
        Simulates scanning multiple pages by creating empty PDF files.

        Args:
            device_name: Device name.
            dpi: Resolution.
            color_mode: Color mode.
            source: Paper source.
            duplex_mode: Duplex mode.
            page_format: Paper format.
            progress_callback: Optional progress callback.

        Returns:
            List of mock file paths.
        """
        paths: List[str] = []
        count = 1 if "ADF" not in source else 2
        for i in range(count):
            fd, path = tempfile.mkstemp(suffix=".pdf", prefix=f"mock_p{i+1}_")
            with os.fdopen(fd, "wb") as f:
                # Minimal PDF header to satisfy pikepdf/basic checks if needed
                f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000062 00000 n \n0000000117 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF")
            paths.append(path)
        return paths


class SaneScanner(ScannerDriver):
    """
    Implementation of ScannerDriver using the SANE library for Linux.
    """

    def __init__(self) -> None:
        """Initializes the SANE library if available."""
        if SANE_AVAILABLE:
            try:
                sane.init()
            except Exception as e:
                print(f"SANE init failed: {e}")

    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        """
        Lists available SANE devices.

        Returns:
            A list of tuples containing (name, vendor, model, type).
        """
        if not SANE_AVAILABLE:
            return []
        try:
            # SANE discovery can be flaky; re-init sometimes helps find devices that just went online
            try:
                sane.init()
            except Exception:
                pass
            devices = sane.get_devices()
            print(f"[DEBUG] SANE discovered {len(devices)} devices: {devices}")
            return devices
        except Exception as e:
            print(f"SANE list_devices error: {e}")
            return []

    def get_source_list(self, device_name: str) -> List[str]:
        """
        Returns a list of supported sources for the given device.

        Args:
            device_name: The name of the SANE device.

        Returns:
            A list of supported source strings.
        """
        if not SANE_AVAILABLE:
            return ["Flatbed"]
        try:
            import time

            time.sleep(0.2)  # Give device a moment
            dev = sane.open(device_name)
            opts = {opt[1]: opt for opt in dev.get_options()}
            print(f"DEBUG: All SANE options for {device_name}: {list(opts.keys())}")
            sources = []
            if "source" in opts:
                try:
                    sources = opts["source"][8]
                except Exception as e:
                    print(f"DEBUG: Could not read source list: {e}")
                    sources = ["Flatbed"]
            dev.close()
            return sources
        except Exception as e:
            print(f"DEBUG: get_source_list failed for {device_name}: {e}")
            return ["Flatbed", "ADF"]

    def get_resolution_list(self, device_name: str) -> List[int]:
        """
        Returns a list of supported resolutions (DPI) for the given device.

        Args:
            device_name: The name of the SANE device.

        Returns:
            A list of supported resolutions in DPI.
        """
        if not SANE_AVAILABLE:
            return [75, 150, 200, 300, 600]
        try:
            import time

            time.sleep(0.1)
            dev = sane.open(device_name)
            opts = {opt[1]: opt for opt in dev.get_options()}
            resolutions = []
            if "resolution" in opts:
                opt = opts["resolution"]
                constraint_type = opt[4]
                constraint = opt[8]

                if constraint_type == 1:  # Range
                    # (min, max, quant)
                    min_val, max_val, quant = constraint
                    if quant <= 0:
                        quant = 50
                    resolutions = list(range(int(min_val), int(max_val) + 1, int(quant)))
                elif constraint_type == 2:  # List
                    resolutions = [int(v) for v in constraint]

            dev.close()
            
            if not resolutions:
                resolutions = [75, 150, 200, 300, 600]
            
            return sorted(list(set(resolutions)))
        except Exception as e:
            print(f"DEBUG: get_resolution_list failed for {device_name}: {e}")
            return [75, 150, 200, 300, 600]

    def scan_page(self, device_name: str, dpi: int = 200, color_mode: str = "Color") -> Optional[str]:
        """
        Scans a single page using the Flatbed source.

        Args:
            device_name: The name of the SANE device.
            dpi: Resolution.
            color_mode: Color mode.

        Returns:
            The path to the scanned page, or None if failed.
        """
        pages = self.scan_pages(device_name, dpi, color_mode, source="Flatbed")
        return pages[0] if pages else None

    def scan_pages(
        self,
        device_name: str,
        dpi: int = 200,
        color_mode: str = "Color",
        source: str = "Flatbed",
        duplex_mode: str = "LongEdge",
        page_format: str = "A4",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[str]:
        """
        Scans multiple pages using either scanimage (batch) or python-sane loop.

        Args:
            device_name: The name of the SANE device.
            dpi: Resolution.
            color_mode: Color mode.
            source: Paper source.
            duplex_mode: Duplex configuration.
            page_format: Paper format.
            progress_callback: Optional progress callback.

        Returns:
            A list of temporary file paths for the scanned pages.
        """
        # 1. Automatic Duplex Flag
        is_adf = any(kw in source for kw in ["ADF", "Feeder", "Einzug"])
        is_duplex = any(kw in source for kw in ["Duplex", "Beidseitig", "Zweiseitig"])

        has_duplex_opt = False
        if SANE_AVAILABLE:
            try:
                dev = sane.open(device_name)
                opts = {opt[1]: opt for opt in dev.get_options()}
                if "duplex" in opts:
                    has_duplex_opt = True
                dev.close()
            except Exception as e:
                print(f"DEBUG: Could not check duplex capability: {e}")

        # 2. Geometry / Page Size
        geom_args: List[str] = []
        if page_format == "A4":
            geom_args = ["-x", "210mm", "-y", "297mm"]
        elif page_format == "Letter":
            geom_args = ["-x", "215.9mm", "-y", "279.4mm"]
        elif page_format == "Legal":
            geom_args = ["-x", "215.9mm", "-y", "355.6mm"]

        # 3. STRATEGY: For ADF/Duplex, 'scanimage --batch' is much more reliable
        if is_adf:
            extra_args = list(geom_args)
            if is_duplex and has_duplex_opt:
                extra_args.append("--duplex=yes")

            try:
                import time

                time.sleep(0.5)  # Prevent "Device busy" between discovery and scan
                results = self._scan_via_scanimage(device_name, dpi, color_mode, source, extra_args, progress_callback, page_format)
                if results:
                    return results
            except Exception as e:
                print(f"SANE: scanimage batch failed ({e}), falling back to python-sane loop...")

        # FALLBACK: python-sane loop
        return self._scan_via_python_sane(device_name, dpi, color_mode, is_adf, is_duplex, source, duplex_mode, progress_callback)

    def _scan_via_scanimage(
        self,
        device: str,
        dpi: int,
        mode: str,
        source: str,
        extra_args: List[str],
        progress_callback: Optional[Callable[[int, int], None]],
        page_format: str,
    ) -> List[str]:
        """
        Executes scanimage --batch to scan multiple pages efficiently.
        Handles image conversion and normalization to target page formats.

        Args:
            device: SANE device name.
            dpi: Resolution.
            mode: Color mode.
            source: Paper source.
            extra_args: Additional scanimage arguments.
            progress_callback: Optional progress callback.
            page_format: Target paper format.

        Returns:
            A list of temporary file paths for the scanned pages.
        """
        temp_dir = tempfile.mkdtemp(prefix="kpaper_scan_")
        pattern = os.path.join(temp_dir, "p%d.tif")

        # Adjust mode name (some drivers use lowercase)
        mode_val = mode

        cmd = [
            "scanimage",
            "-d",
            device,
            "--source",
            source,
            "--resolution",
            str(dpi),
            "--mode",
            mode_val,
            "--batch=" + pattern,
            "--format=tiff",
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

            # After process finishes, capture results and errors
            stdout, stderr = process.communicate()
            if process.returncode != 0 or not glob.glob(os.path.join(temp_dir, "*.tif")):
                print(f"ERROR: scanimage failed (Exit {process.returncode})")
                if stderr:
                    print(f"SANE Stderr: {stderr.strip()}")
                if stdout:
                    print(f"SANE Stdout: {stdout.strip()}")
        except Exception as e:
            print(f"ERROR calling scanimage: {e}")
            return []

        results: List[str] = []
        tif_files = sorted(glob.glob(os.path.join(temp_dir, "*.tif")), key=lambda x: int(os.path.basename(x)[1:-4]))

        for i, tif in enumerate(tif_files):
            try:
                pdf_path = os.path.join(temp_dir, f"scan_p{i+1}.pdf")
                with Image.open(tif) as im:
                    # PIXEL-LEVEL A4 NORMALIZER (Width-Anchor)
                    if page_format == "A4":
                        print("\n--- A4 NORMALIZER DEBUG (Width-Anchor) ---")
                        target_w_mm, target_h_mm = 210.0, 297.0

                        # Get reliable DPI
                        info_dpi = im.info.get("dpi")
                        res_unit = im.info.get("resolution_unit", 2)  # 2: inch, 3: cm
                        cur_dpi = float(info_dpi[0]) if (info_dpi and info_dpi[0] > 0) else float(dpi)

                        if res_unit == 3:  # Normalize to DPI
                            cur_dpi = cur_dpi * 2.54

                        # Calculate target pixel dimensions for A4
                        target_w_px = int(round((target_w_mm / 25.4) * cur_dpi))
                        target_h_px = int(round((target_h_mm / 25.4) * cur_dpi))

                        # 1. Scale based on width (Anchor)
                        scale_factor = target_w_px / im.width
                        scaled_h = int(round(im.height * scale_factor))

                        print(f"I.  Input: {im.width}x{im.height} px at {cur_dpi:.1f} DPI")
                        print(f"II. Scale: Width mapping to {target_w_px}px (Factor {scale_factor:.4f})")

                        im = im.resize((target_w_px, scaled_h), Image.Resampling.LANCZOS)

                        # 2. Crop to exactly A4 height
                        if im.height > target_h_px:
                            excess = im.height - target_h_px
                            print(f"III. [CROP] Removing {excess} px from bottom to reach {target_h_px}px (297mm).")
                            im = im.crop((0, 0, target_w_px, target_h_px))
                        else:
                            print(f"III. [PAD/SKIP] Height {im.height} fits within A4 {target_h_px}.")

                        save_resolution = float(cur_dpi)
                        print(f"IV. Result: {im.width}x{im.height} px (A4 Standard)\n")
                    else:
                        save_resolution = float(im.info.get("dpi", (dpi, dpi))[0])

                    if im.mode != "RGB":
                        im = im.convert("RGB")

                    im.save(pdf_path, "PDF", resolution=save_resolution)
                results.append(pdf_path)
            except Exception as e:
                print(f"ERROR converting {tif} to PDF: {e}")
            finally:
                try:
                    if os.path.exists(tif):
                        os.remove(tif)
                except Exception as e:
                    print(f"DEBUG: Could not remove temp tif {tif}: {e}")

        print(f"SANE: scanimage batch finished. Found {len(results)} pages.")
        return results

    def _scan_via_python_sane(
        self,
        device_name: str,
        dpi: int,
        color_mode: str,
        is_adf: bool,
        is_duplex: bool,
        source: str,
        duplex_mode: str,
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> List[str]:
        """
        Scans pages using the python-sane library in a loop.
        Fallback for when batch scanning via scanimage is not available or fails.

        Args:
            device_name: SANE device name.
            dpi: Resolution.
            color_mode: Color mode.
            is_adf: Whether the source is an ADF.
            is_duplex: Whether to scan in duplex mode.
            source: Paper source.
            duplex_mode: Duplex configuration.
            progress_callback: Optional progress callback.

        Returns:
            A list of temporary file paths for the scanned pages.

        Raises:
            RuntimeError: If python-sane is not installed.
        """
        if not SANE_AVAILABLE:
            raise RuntimeError("python-sane not installed.")

        results: List[str] = []
        dev = None
        try:
            dev = sane.open(device_name)
            options = {opt[1]: opt for opt in dev.get_options()}

            if "resolution" in options:
                try:
                    dev.resolution = dpi
                except Exception as e:
                    print(f"DEBUG: Could not set resolution to {dpi}: {e}")
            if "mode" in options:
                try:
                    dev.mode = color_mode
                except Exception as e:
                    print(f"DEBUG: Could not set mode to {color_mode}: {e}")

            if "source" in options:
                # Use exactly the source selected by the user
                try:
                    dev.source = source
                except Exception as e:
                    print(f"DEBUG: Could not set source to {source}: {e}")

            if is_duplex and "duplex" in options:
                try:
                    dev.duplex = True
                except Exception as e:
                    print(f"DEBUG: Could not set duplex: {e}")

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
                    if not is_adf:
                        break
                except Exception as e:
                    print(f"SANE loop break: {e}")
                    break
            return results
        except Exception as e:
            print(f"SANE python-sane error: {e}")
            raise
        finally:
            if dev:
                dev.close()

    def cleanup(self) -> None:
        """Exits the SANE library."""
        if SANE_AVAILABLE:
            try:
                sane.exit()
            except Exception:
                pass


def get_scanner_driver(driver_type: str = "auto") -> ScannerDriver:
    """
    Factory function for scanner drivers.

    Args:
        driver_type: The type of driver ('mock', 'sane', or 'auto').

    Returns:
        An instance of ScannerDriver.
    """
    if driver_type == "mock":
        return MockScanner()
    elif driver_type == "sane":
        return SaneScanner()
    else:
        if SANE_AVAILABLE:
            return SaneScanner()
        else:
            return MockScanner()
