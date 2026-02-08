# Analysis: The Scaling Paradox in QPdfView (Qt6)

## Problem Description
The "Scaling Paradox" refers to a reproducible visual discrepancy in the `DualPdfViewerWidget` where two physically identical documents (e.g., DIN A4) do not result in identical visual representations when synchronized in "Fit-to-View" mode.

### Observed Symptoms
- **Native PDF (Vector-based):** `FitInView` calculates an effective zoom factor of **~60%** (for 1200x900 window). The entire page is visible.
- **Scanned PDF (300 DPI Bitmap):** `FitInView` calculates an effective zoom factor of **~95%**. The page is truncated/zoomed-in, and only a portion is visible, even though the viewer claims to be in "Fit" mode.
- **Metadata Identity:** Both files report a logical page size of approximately **595 x 842 points** (Standard A4).

## Diagnostic Data (Collected 2026-02-08)

| configuration | Document Type | Page Points | Effective Zoom | Visual Result |
| :--- | :--- | :--- | :--- | :--- |
| **Left Viewer** | Amazon Invoice (Native) | 595.3 x 841.9 | **0.6033** | **Correct (Full Page)** |
| **Right Viewer** | doc0059... (Scan) | 595.2 x 841.7 | **0.9481** | **Incorrect (Clipped/Zoomed)** |

### Swapping Test
When the documents are swapped (Scan on Left, Native on Right), the behavior follows the file:
- The **Scan** document always forces a higher, incorrect zoom factor (~95%) for "Fit".
- The **Native** document always correctly calculates the zoom factor (~60%).

## Root Cause Analysis

### 1. High-DPI vs. Logical Points
A 300 DPI scan has a much higher pixel density than the default PDF "Point" (1/72 inch). 
- **Point:** 1/72 inch (~0.35 mm)
- **300 DPI Pixel:** 1/300 inch (~0.08 mm)

While the PDF specification dictates that the logical coordinate system is point-based, the internal image layer of the scan contains many more samples. 

### 2. Qt6 QPdfView Implementation Flaw
Research and diagnostic tests suggest that `QPdfView` in Qt6 has two significant issues:
1. **The Reporting Bug:** `zoomFactor()` often returns a "legacy" or "default" value (like 1.0 or the last custom value) when `ZoomMode::FitInView` is active, rather than the factor actually being applied.
2. **Viewport Calculation Bias:** When a PDF contains a single, high-resolution bitmap layer that takes up the entire page, `QPdfView`'s internal layout engine appears to be influenced by the image's "native" resolution or its interaction with the screen's DPI, leading to an incorrect viewport-to-document mapping in "Fit" mode.

## Mathematical Paradox
To achieve a visual match, the "Slave" viewer must ignore its own internal `FitInView` calculation and strictly follow a calculated ratio:
```python
Target_Zoom = Master_Effective_Zoom * (Master_Points_Width / Slave_Points_Width) + Delta
```
However, since the **Scan** document's "Fit" calculation (Master side) is already visually incorrect (too large), any Slave following it will also be visually incorrect.

## The Proven Solution: Manual "True Fit" Injection

As of 2026-02-08, a diagnostic test (`test_true_fit_concept.py`) has proven that the paradox can be solved by revoking `QPdfView`'s autonomy.

### Test Results (Manual Injection)
Using the same A4 Native and Scan files:
- **Left (Native) Zoom:** 0.9542
- **Right (Scan) Zoom:** 0.9543
- **Visual Discrepancy:** **Merged to zero.**

By manually performing the fitting calculation based on `doc.pagePointSize()` and forcing `ZoomMode::Custom`, the renderer ignores the internal DPI metadata of the scan and treats one PDF Point as a consistent unit relative to the viewport pixels.

### Implementation Blueprint
1. Set `v.setZoomMode(QPdfView.ZoomMode.Custom)` on all viewers.
2. Install an **Event Filter** on the `viewport()` of each `QPdfView`.
3. On `ResizeEvent`, execute a manual fit:
   ```python
   page_pts = doc.pagePointSize(current_page)
   viewport_size = view.viewport().size()
   zoom = min((viewport_size.width() - 4) / page_pts.width(),
              (viewport_size.height() - 4) / page_pts.height())
   view.setZoomFactor(zoom)
   ```

This method is immune to the "95% vs 60%" paradox because it treats the PDF as a coordinate system first and an image second.

---
*Documented by Antigravity AI Platform*
