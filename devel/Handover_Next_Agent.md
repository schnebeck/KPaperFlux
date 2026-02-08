# **Handover: Current Task State**

## **Status Overview (as of 2026-02-07)**
We are currently in a **Coding Lock** state while investigating a persistent discrepancy in the **PDF Sync Arithmetics**. Although a Master-Follower logic based on millimeters has been implemented, it still fails to produce identical visual results ("Fit" to fullscreen) on both sides in some real-world scenarios.

---

## **Current Challenge: The "Scaling Paradox"**
*   **The Problem:** Two physically identical DIN A4 documents do not result in identical "Fit-In-View" representations when synchronized.
*   **Current Hypothesis:** There is a mismatch between the reported "Page Points" (metadata) and the actual "Viewport Geometry" (rendering). Even with synchronized scrollbar policies, the right viewer often displays the document at a different scale than the left.
*   **What was tried:** 
    *   Point-to-Millimeter conversion.
    *   Proportional (percentage-based) scroll synchronization.
    *   Forced scrollbar-policy matching to equalize viewport sizes.

---

## **Recent Achievements (Validated but not final)**
1.  **Background Processing:** `MatchAnalysisWorker` (background thread) successfully pre-calculates image-based differences (CV2 overlays) without freezing the GUI.
2.  **Infrastructure:** Core `DualPdfViewerWidget` structure is stable and supports Master-Follower switching.
3.  **Testing:** Basic unit tests in `tests/unit/test_pdf_delta_sync.py` pass, but they use Mocks. The "real-world" PDF parameters seem to deviate from these mocks.

---

## **The Next Task (After Debugging is resolved)**
1.  **Finalize Sync Math:** Determine why `effective_zoom_factor` + `Ratio` does not yet lead to 1:1 visual identity.
2.  **Plugin System Implementation:** Start `core/plugins/` infrastructure as per `devel/Plugin_System_Spec.md`.
3.  **Hybrid Verification:** OCR vs. Visual verification of the CV2-detected deltas.

---

## **Known "Mängel" (Bugs & Issues)**
*   **Sync Drift:** Right viewer does not reliably enter "Fullscreen" even if Master is "Fit".
*   **Qt Warnings:** `nullptr` parameter warnings during `QPdfLinkModel` initialization.
*   **Coding Lock:** Active. No code changes without joining the discussion/debugging session with the user.

---

## **Environment**
*   **OS:** Linux (KDE Plasma)
*   **Tools:** PyQt6, PyMuPDF (fitz), OpenCV (cv2)
*   **Workcase:** Comparing scanned documents (Potential UserUnit issues or metadata pollution).

---
*End of Handover Documentation*
