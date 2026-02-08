
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

    def calculate_pair_score(self, scan_path: str, native_path: str) -> float:
        """
        Calculates a matching 'distance' score between a scan and a native PDF.
        Lower scores = better alignment.
        """
        try:
            doc_scan = fitz.open(scan_path)
            doc_native = fitz.open(native_path)
            
            if len(doc_scan) < 1 or len(doc_native) < 1: return float('inf')
            
            mat = fitz.Matrix(1.0, 1.0)
            pix_scan = doc_scan[0].get_pixmap(matrix=mat)
            pix_native = doc_native[0].get_pixmap(matrix=mat)
            
            img_scan = self.pixmap_to_cv_image(pix_scan)
            img_native = self.pixmap_to_cv_image(pix_native)
            
            gray_native = cv2.cvtColor(img_native, cv2.COLOR_BGR2GRAY)
            gray_scan = cv2.cvtColor(img_scan, cv2.COLOR_BGR2GRAY)
            
            orb = cv2.ORB_create(3000)
            kp1, des1 = orb.detectAndCompute(gray_native, None)
            kp2, des2 = orb.detectAndCompute(gray_scan, None)
            
            if des1 is None or des2 is None: return float('inf')
            
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = matcher.match(des1, des2)
            matches = sorted(matches, key=lambda x: x.distance)
            good_matches = matches[:int(len(matches) * 0.20)]
            
            if len(good_matches) < 4: return float('inf')
            
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            
            M, _ = cv2.estimateAffine2D(dst_pts, src_pts, method=cv2.RANSAC, ransacReprojThreshold=5.0)
            if M is None: return float('inf')
            
            height, width = gray_native.shape
            aligned_scan = cv2.warpAffine(img_scan, M, (width, height))
            
            gray_aligned = cv2.cvtColor(aligned_scan, cv2.COLOR_BGR2GRAY)
            
            _, native_text_mask = cv2.threshold(gray_native, 200, 255, cv2.THRESH_BINARY_INV)
            kernel = np.ones((3,3), np.uint8)
            native_text_mask = cv2.dilate(native_text_mask, kernel, iterations=2)
            
            _, scan_ink_mask = cv2.threshold(gray_aligned, 205, 255, cv2.THRESH_BINARY_INV)
            
            diff_mask = cv2.bitwise_and(scan_ink_mask, scan_ink_mask, mask=cv2.bitwise_not(native_text_mask))
            diff_mask = cv2.morphologyEx(diff_mask, cv2.MORPH_OPEN, kernel)
            
            score = cv2.countNonZero(diff_mask)
            
            doc_scan.close()
            doc_native.close()
            return score
        except Exception:
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
    def align_and_compare_base(img_native: np.ndarray, img_scan: np.ndarray) -> Tuple[np.ndarray, float]:
        """Base implementation of ORB alignment."""
        gray_native = cv2.cvtColor(img_native, cv2.COLOR_BGR2GRAY)
        gray_scan = cv2.cvtColor(img_scan, cv2.COLOR_BGR2GRAY)

        orb = cv2.ORB_create(10000)
        kp1, des1 = orb.detectAndCompute(gray_native, None)
        kp2, des2 = orb.detectAndCompute(gray_scan, None)

        if des1 is None or des2 is None:
            return img_scan, 0.0

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        matches = sorted(matches, key=lambda x: x.distance)

        good_matches = matches[:int(len(matches) * 0.20)]
        if len(good_matches) < 4:
            return img_scan, 0.0

        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        M, _ = cv2.estimateAffine2D(dst_pts, src_pts, method=cv2.RANSAC, ransacReprojThreshold=5.0)
        if M is None:
            return img_scan, 0.0

        h, w = gray_native.shape
        img_scan_aligned = cv2.warpAffine(img_scan, M, (w, h))

        diff = cv2.absdiff(gray_native, cv2.cvtColor(img_scan_aligned, cv2.COLOR_BGR2GRAY))
        _, diff_thresh = cv2.threshold(diff, 35, 255, cv2.THRESH_BINARY)
        non_zero_count = np.count_nonzero(diff_thresh)
        similarity = 1.0 - (non_zero_count / (w * h))

        return img_scan_aligned, similarity

    @staticmethod
    def align_and_compare(img_native: np.ndarray, img_scan: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Aligns img_scan to img_native with automatic 4-way rotation fallback.
        Checks 0, 90, 180, 270 degrees.
        """
        best_img, best_sim = HybridEngine.align_and_compare_base(img_native, img_scan)
        
        # If match is poor (< 0.85), check rotations
        if best_sim < 0.85:
            # Check 180, 90, 270
            for rot in [cv2.ROTATE_180, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE]:
                img_rot = cv2.rotate(img_scan, rot)
                aligned, sim = HybridEngine.align_and_compare_base(img_native, img_rot)
                if sim > best_sim + 0.1:
                    best_img, best_sim = aligned, sim
                    if best_sim > 0.95: break
                
        return best_img, best_sim

    @staticmethod
    def create_diff_overlay(img_native: np.ndarray, img_scan_aligned: np.ndarray) -> np.ndarray:
        """
        Advanced ROI-based diff extraction.
        1. Identifies 'Ink' in Scan that isn't 'Text' in Native.
        2. Groups pixels into blobs (signatures/stamps).
        3. Discards small artifacts (DPI-aware noise reduction).
        """
        h, w = img_native.shape[:2]
        gray_native = cv2.cvtColor(img_native, cv2.COLOR_BGR2GRAY)
        gray_scan = cv2.cvtColor(img_scan_aligned, cv2.COLOR_BGR2GRAY)

        # 1. Native Mask (Dilated for tolerance)
        _, native_text_mask = cv2.threshold(gray_native, 200, 255, cv2.THRESH_BINARY_INV)
        kernel_dilate = np.ones((3,3), np.uint8)
        native_text_mask_dilated = cv2.dilate(native_text_mask, kernel_dilate, iterations=2)

        # 2. Scan Ink Mask
        _, scan_ink_mask = cv2.threshold(gray_scan, 205, 255, cv2.THRESH_BINARY_INV)

        # 3. Raw Difference
        raw_diff_mask = cv2.bitwise_and(scan_ink_mask, scan_ink_mask, mask=cv2.bitwise_not(native_text_mask_dilated))

        # 4. ROI Validation (Morphological closing to bridge gaps in strokes)
        kernel_close = np.ones((5,5), np.uint8)
        connected_mask = cv2.morphologyEx(raw_diff_mask, cv2.MORPH_CLOSE, kernel_close)
        contours, _ = cv2.findContours(connected_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        final_roi_mask = np.zeros_like(raw_diff_mask)
        min_area = 150 # Adjustable area threshold
        
        for cnt in contours:
            if cv2.contourArea(cnt) > min_area:
                # Add this validated area to the final mask
                cv2.drawContours(final_roi_mask, [cnt], -1, 255, -1)

        # 5. Build Final Display Overlay
        # Neutral background
        overlay = np.full((h, w, 3), 255, dtype=np.uint8)
        # Faint gray for identical parts (where both have 'ink')
        both_ink = cv2.bitwise_and(native_text_mask, scan_ink_mask)
        overlay[both_ink > 0] = [245, 245, 245]
        
        # Color Highlights based on the ROI mask
        # Validated differences (Signatures, Stamps) in Red
        overlay[final_roi_mask > 0] = [0, 0, 220] 
        
        # Original text that is MISSING in scan (Cyan)
        missing_mask = cv2.subtract(native_text_mask, scan_ink_mask)
        overlay[missing_mask > 0] = [200, 200, 0] 
        
        return overlay
