
import cv2
import numpy as np
import fitz
from typing import Tuple, Optional
import os

class HybridEngine:
    """
    Engine for comparing and aligning documents.
    Specifically designed to align a 'Born-Digital' (Native) PDF page 
    with a 'Scanned/Signed' counterpart.
    """

    @staticmethod
    def pixmap_to_cv_image(pix: fitz.Pixmap) -> np.ndarray:
        """Converts a fitz Pixmap to an OpenCV BGR image."""
        img_data = np.frombuffer(pix.samples, dtype=np.uint8)
        if pix.n == 4:
            img = img_data.reshape(pix.height, pix.width, 4)
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            img = img_data.reshape(pix.height, pix.width, 3)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        else:
            img = img_data.reshape(pix.height, pix.width)
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        return img

    def is_digital_born(self, doc_path: str) -> bool:
        """
        Heuristic: Checks if a PDF is 'Digital Born' (Native) or a Scan.
        Native PDFs have vector text and perfect backgrounds.
        """
        try:
            doc = fitz.open(doc_path)
            if len(doc) < 1: return False
            page = doc[0]
            
            # 1. Check for Text Layer
            text = page.get_text()
            if len(text) > 50: 
                return True

            # 2. Noise/Brightness Analysis
            mat = fitz.Matrix(0.5, 0.5) 
            pix = page.get_pixmap(matrix=mat)
            img = self.pixmap_to_cv_image(pix)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            bright_pixels = gray[gray > 200]
            if len(bright_pixels) == 0: return False
            
            std_dev = np.std(bright_pixels)
            doc.close()
            
            return std_dev < 2.0
        except Exception:
            return False

    def calculate_pair_score(self, scan_path: str, native_path: str, 
                             native_img_cached: np.ndarray = None, 
                             scan_img_cached: np.ndarray = None,
                             kp_native_cached = None,
                             des_native_cached = None,
                             kp_scan_cached = None,
                             des_scan_cached = None,
                             dpi: int = 150) -> float:
        """
        Calculates a matching 'distance' score.
        Accepts DPI parameter for two-stage matching (Fast 72 DPI or Precise 150 DPI).
        """
        try:
            # 1. Get Images (from cache or file)
            if scan_img_cached is not None:
                img_scan_raw = scan_img_cached
            else:
                doc_scan = fitz.open(scan_path)
                img_scan_raw = self.pdf_page_to_numpy(doc_scan, 0, dpi=dpi)
                doc_scan.close()
            
            if native_img_cached is not None:
                img_native = native_img_cached
            else:
                doc_native = fitz.open(native_path)
                img_native = self.pdf_page_to_numpy(doc_native, 0, dpi=dpi)
                doc_native.close()
            
            # 2. Align (Optimized)
            img_scan_aligned, sim_score = self.align_and_compare(
                img_native, img_scan_raw,
                kp_native=kp_native_cached,
                des_native=des_native_cached,
                kp_scan=kp_scan_cached,
                des_scan=des_scan_cached
            )
            
            if sim_score < 0.50: return 1000000.0
            
            # 3. Ink Recall Analysis
            gray_native = cv2.cvtColor(img_native, cv2.COLOR_BGR2GRAY)
            gray_aligned = cv2.cvtColor(img_scan_aligned, cv2.COLOR_BGR2GRAY)
            
            _, native_text_mask = cv2.threshold(gray_native, 215, 255, cv2.THRESH_BINARY_INV)
            native_ink_count = cv2.countNonZero(native_text_mask)
            
            if native_ink_count < 20: return 500000.0

            _, scan_ink_mask = cv2.threshold(gray_aligned, 205, 255, cv2.THRESH_BINARY_INV)
            # Use conservative dilation: 1 iter is usually enough for alignment jitter
            # but preserve character shapes to distinguish similar text.
            dil_iter = 1 
            scan_ink_dilated = cv2.dilate(scan_ink_mask, None, iterations=dil_iter) 
            
            overlap = cv2.bitwise_and(native_text_mask, scan_ink_dilated)
            recall = cv2.countNonZero(overlap) / native_ink_count
            
            # 4. Strict Recall (No dilation) for fine-grained tie-breaking
            overlap_strict = cv2.bitwise_and(native_text_mask, scan_ink_mask)
            recall_strict = cv2.countNonZero(overlap_strict) / native_ink_count
            
            # Weighted Distance: Prioritize ink recall over structural similarity
            # recall_strict is very sensitive to alignment, so we use it as a 
            # powerful tie-breaker for layouts that are almost identical.
            distance = (1.0 - recall) * 12000.0 + \
                       (1.0 - recall_strict) * 6000.0 + \
                       (1.0 - sim_score) * 2000.0
            
            return distance
        except Exception as e:
            print(f"[HybridEngine] Score Calculation Failed: {e}")
            return float('inf')

    @staticmethod
    def pdf_page_to_numpy(doc: fitz.Document, page_num: int, dpi: int = 200) -> np.ndarray:
        """Renders a PDF page to a numpy BGR image (OpenCV format)."""
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        
        # Convert to numpy
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        
        if pix.n == 3: # RGB
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif pix.n == 4: # RGBA
            return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        else:
            return img

    @staticmethod
    def get_orb_features(img: np.ndarray, max_points: int = 1500) -> Tuple[list, np.ndarray]:
        """Precomputes ORB features for an image (Optimized to 1500 points)."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        orb = cv2.ORB_create(max_points)
        kp, des = orb.detectAndCompute(gray, None)
        return kp, des

    @staticmethod
    def align_and_compare_base(img_native: np.ndarray, img_scan: np.ndarray, 
                               kp_native=None, des_native=None, 
                               kp_scan=None, des_scan=None) -> Tuple[np.ndarray, float]:
        """Base implementation of ORB alignment with optional cached features."""
        gray_native = cv2.cvtColor(img_native, cv2.COLOR_BGR2GRAY) if len(img_native.shape) == 3 else img_native
        gray_scan = cv2.cvtColor(img_scan, cv2.COLOR_BGR2GRAY) if len(img_scan.shape) == 3 else img_scan

        # Use provided features or compute on the fly
        if kp_native is None or des_native is None:
            kp1, des1 = HybridEngine.get_orb_features(gray_native)
        else:
            kp1, des1 = kp_native, des_native
            
        if kp_scan is None or des_scan is None:
            kp2, des2 = HybridEngine.get_orb_features(gray_scan)
        else:
            kp2, des2 = kp_scan, des_scan

        if des1 is None or des2 is None: return img_scan, 0.0

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        try:
            matches = bf.match(des1, des2)
        except Exception:
            return img_scan, 0.0
            
        if not matches: return img_scan, 0.0
        
        matches = sorted(matches, key=lambda x: x.distance)
        good_matches = matches[:int(len(matches) * 0.35)] # Increased slightly for robustness

        if len(good_matches) < 7: return img_scan, 0.0

        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        # Use Homography instead of Affine to handle aspect ratio differences (A4 vs Letter)
        # and perspective distortions (8 degrees of freedom).
        H, _ = cv2.findHomography(dst_pts, src_pts, method=cv2.RANSAC, ransacReprojThreshold=4.0)
        if H is None: return img_scan, 0.0

        h_n, w_n = gray_native.shape
        # apply WarpPerspective for full "Entzerrung"
        img_scan_aligned = cv2.warpPerspective(img_scan, H, (w_n, h_n))

        # Precision Similarity Check (Resolution scales with DPI)
        cmp_res = 512 if gray_native.shape[0] > 1500 else 256
        s_native = cv2.resize(gray_native, (cmp_res, cmp_res))
        
        # Ensure s_scan is also grayscale for comparison
        raw_aligned_gray = cv2.cvtColor(img_scan_aligned, cv2.COLOR_BGR2GRAY) if len(img_scan_aligned.shape) == 3 else img_scan_aligned
        s_scan = cv2.resize(raw_aligned_gray, (cmp_res, cmp_res))
        
        diff = cv2.absdiff(s_native, s_scan)
        # Use lower threshold for higher resolution to catch text differences
        thresh_val = 35 if cmp_res == 512 else 40
        _, diff_thresh = cv2.threshold(diff, thresh_val, 255, cv2.THRESH_BINARY)
        non_zero_count = np.count_nonzero(diff_thresh)
        similarity = 1.0 - (non_zero_count / (cmp_res * cmp_res))

        return img_scan_aligned, similarity

    @staticmethod
    def align_and_compare(img_native: np.ndarray, img_scan: np.ndarray, 
                          kp_native=None, des_native=None,
                          kp_scan=None, des_scan=None) -> Tuple[np.ndarray, float]:
        """
        Aligns a scan with a native image.
        1. Normalizes aspect ratio (Portrait vs Landscape).
        2. Tries 0° and 180° rotations based on similarity scores.
        """
        # --- 1. Orientation Pre-check (Landscape vs Portrait) ---
        h_n, w_n = img_native.shape[:2]
        h_s, w_s = img_scan.shape[:2]
        
        native_is_landscape = w_n > h_n
        scan_is_landscape = w_s > h_s
        
        current_scan = img_scan
        if native_is_landscape != scan_is_landscape:
            # Rotate 90 degrees to match orientation
            current_scan = cv2.rotate(img_scan, cv2.ROTATE_90_CLOCKWISE)
            # Update scan features if they were cached for the original orientation
            kp_s, des_s = None, None 
        else:
            kp_s, des_s = kp_scan, des_scan

        # --- 2. Try Alignment at 0° ---
        best_img, best_sim = HybridEngine.align_and_compare_base(
            img_native, current_scan, 
            kp_native=kp_native, des_native=des_native,
            kp_scan=kp_s, des_scan=des_s
        )
        
        if best_sim > 0.92:
            return best_img, best_sim
            
        # --- 3. Try 180° Rotation (Optimization for Upside Down scans) ---
        img_180 = cv2.rotate(current_scan, cv2.ROTATE_180)
        aligned_180, sim_180 = HybridEngine.align_and_compare_base(
            img_native, img_180, 
            kp_native=kp_native, des_native=des_native
        )
        
        if sim_180 > best_sim:
            best_img, best_sim = aligned_180, sim_180
                
        return best_img, best_sim

    @staticmethod
    def create_diff_overlay(img_native: np.ndarray, img_scan_aligned: np.ndarray) -> np.ndarray:
        """
        High-fidelity Diff Overlay.
        Applies ROI validation to BOTH directions to eliminate alignment artifacts.
        - Red: Added in Scan (Signatures/Stamps)
        - Cyan: Missing in Scan (Deleted text)
        """
        h, w = img_native.shape[:2]
        gray_native = cv2.cvtColor(img_native, cv2.COLOR_BGR2GRAY)
        gray_scan = cv2.cvtColor(img_scan_aligned, cv2.COLOR_BGR2GRAY)

        # 1. Prepare Masks with tolerance (Dilate to ignore 1-2px shifts)
        kernel_tol = np.ones((3,3), np.uint8)
        
        _, native_ink = cv2.threshold(gray_native, 200, 255, cv2.THRESH_BINARY_INV)
        native_ink_dilated = cv2.dilate(native_ink, kernel_tol, iterations=1)
        
        _, scan_ink = cv2.threshold(gray_scan, 205, 255, cv2.THRESH_BINARY_INV)
        scan_ink_dilated = cv2.dilate(scan_ink, kernel_tol, iterations=1)

        # 2. Raw Differences
        added_raw = cv2.bitwise_and(scan_ink, scan_ink, mask=cv2.bitwise_not(native_ink_dilated))
        missing_raw = cv2.bitwise_and(native_ink, native_ink, mask=cv2.bitwise_not(scan_ink_dilated))

        # 3. ROI Validation Helper
        def validate_mask(mask, min_area):
            kernel_close = np.ones((5,5), np.uint8)
            connected = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)
            contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            validated = np.zeros_like(mask)
            for cnt in contours:
                if cv2.contourArea(cnt) > min_area:
                    cv2.drawContours(validated, [cnt], -1, 255, -1)
            return cv2.bitwise_and(mask, validated)

        # Apply validation (Stamps/Signatures need more area, text changes can be smaller)
        added_clean = validate_mask(added_raw, min_area=150)
        missing_clean = validate_mask(missing_raw, min_area=30) # Capture even single letters

        # 4. Build Display Overlay
        # Start with a clean white background
        overlay = np.full((h, w, 3), 255, dtype=np.uint8)
        
        # Identical parts (Light Gray background)
        both_ink = cv2.bitwise_and(native_ink, scan_ink)
        overlay[both_ink > 0] = [230, 230, 230]
        
        # Red: Added (Signatures) - BGR
        overlay[added_clean > 0] = [0, 0, 220]
        
        # Cyan: Missing (Deletions) - BGR
        overlay[missing_clean > 0] = [200, 200, 0]
        
        return overlay

    @staticmethod
    def extract_high_fidelity_overlay(img_native: np.ndarray, img_scan_aligned: np.ndarray) -> Tuple[Optional[np.ndarray], int]:
        """
        Extracts signatures/stamps as a transparent RGBA image.
        Returns (rgba_image, pixel_count).
        """
        h, w = img_native.shape[:2]
        gray_native = cv2.cvtColor(img_native, cv2.COLOR_BGR2GRAY)
        gray_scan = cv2.cvtColor(img_scan_aligned, cv2.COLOR_BGR2GRAY)

        # 1. Native Mask
        _, native_text_mask = cv2.threshold(gray_native, 200, 255, cv2.THRESH_BINARY_INV)
        kernel_dilate = np.ones((3,3), np.uint8)
        native_text_mask_dilated = cv2.dilate(native_text_mask, kernel_dilate, iterations=2)

        # 2. Scan Ink Mask
        _, scan_ink_mask = cv2.threshold(gray_scan, 205, 255, cv2.THRESH_BINARY_INV)

        # 3. Raw Difference
        raw_diff_mask = cv2.bitwise_and(scan_ink_mask, scan_ink_mask, mask=cv2.bitwise_not(native_text_mask_dilated))

        # 4. ROI Validation
        kernel_close = np.ones((5,5), np.uint8)
        connected_mask = cv2.morphologyEx(raw_diff_mask, cv2.MORPH_CLOSE, kernel_close)
        contours, _ = cv2.findContours(connected_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        final_roi_mask = np.zeros_like(raw_diff_mask)
        min_area = 200

        for cnt in contours:
            if cv2.contourArea(cnt) > min_area:
                # Mask specifies which scan pixels to keep
                cv2.drawContours(final_roi_mask, [cnt], -1, 255, -1)

        pixel_count = cv2.countNonZero(final_roi_mask)
        if pixel_count < 100:
            return None, 0

        # Fine-tune mask: only keep actual ink pixels from the scan inside the ROI
        extracted_ink_mask = cv2.bitwise_and(raw_diff_mask, final_roi_mask)

        # 5. Build RGBA Overlay
        b, g, r = cv2.split(img_scan_aligned)
        
        # Optimization: Clear ignored pixels to improve PNG compression
        b = cv2.bitwise_and(b, b, mask=extracted_ink_mask)
        g = cv2.bitwise_and(g, g, mask=extracted_ink_mask)
        r = cv2.bitwise_and(r, r, mask=extracted_ink_mask)
        
        overlay = cv2.merge([b, g, r, extracted_ink_mask])
        return overlay, pixel_count
