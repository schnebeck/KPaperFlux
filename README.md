<div align="center">
  <img src="resources/icon.png" alt="KPaperFlux Logo" width="128" height="128">
  <h1 align="center">KPaperFlux</h1>
  <p align="center">
    <strong>From Paper to Power: Forensic AI Document Intelligence</strong><br>
    <em>The ultimate semantic bridge between physical paperwork and structured data.</em>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/Status-Active_Development-green" alt="Status">
    <img src="https://img.shields.io/badge/Python-3.12+-blue" alt="Python">
    <img src="https://img.shields.io/badge/UI-PyQt6_Premium-orange" alt="UI">
    <img src="https://img.shields.io/badge/AI-Gemini_2.0_Flash-red" alt="AI">
  </p>
</div>

---

## 🦅 Why KPaperFlux?

Most document management systems are just glorified folders. **KPaperFlux is a different beast.** It doesn't just store your files; it **understands** them with forensic precision.

*   **Forensic "X-Ray" Vision:** See through your documents. We separate stamps, signatures, and handwritten notes from the core data for 100% extraction accuracy.
*   **Semantic DNA:** Every document is transformed into a standardized Digital Twin (EN 16931/ZUGFeRD), ready for accounting, analytics, and automation.
*   **Privacy First, AI Powered:** Experience the cutting-edge power of Google Gemini while maintaining absolute local control over your physical document vault.
*   **Data you can Trust:** Built-in mathematical validation engines cross-check every cent and every tax rate. No hallucinations, just facts.

---

## 🖼️ Showcase: Intelligence in Action

<p align="center">
  <img src="docs/screenshots/dashboard_main.png" alt="Dynamic Dashboard" width="800"><br>
  <em>The new Dynamic Dashboard: Real-time analytics with pattern-aware visualizations.</em>
</p>

<table align="center">
  <tr>
    <td align="center"><b>Forensic Audit</b><br><img src="docs/screenshots/audit_forensics.png" width="380"></td>
    <td align="center"><b>Multi-Format Export</b><br><img src="docs/screenshots/multiformat_export.png" width="380"></td>
  </tr>
  <tr>
    <td align="center"><b>Smart Analytics</b><br><img src="docs/screenshots/pie_chart_detail.png" width="380"></td>
    <td align="center"><b>Precision Search</b><br><img src="docs/screenshots/smart_filtering.png" width="380"></td>
  </tr>
</table>

---

---

## 🔥 Technical Highlights

### 🧠 Semantic Analysis Pipeline
*   **Multi-Stage Extraction:** Uses an adaptive pipeline (Stage 1 to 2) to classify documents and extract structured JSON compliant with **EN 16931 (ZUGFeRD 2.2)**.
*   **Visual Auditor (X-Ray):** Separates visual artifacts (accounting stamps, handwritten "Paid" notes, signatures) from the background text for independent analysis.
*   **Mathematical Integrity:** Automated cross-checking of net/tax/gross totals to ensure 100% calculation consistency.

### 📄 Professional PDF Rendering
*   **Re-Materialization:** Generates high-quality, DIN 5008 compliant PDF documents from semantic data.
*   **Advanced Layouting:** Dynamic column calculation for item lists, automatic pagination, and specialized support for certificates (RoHS, REACH) and legal statements.

### 🧩 Hybrid PDF & Forensic Trust
*   **Vector Protection:** Instead of "baking" scans into PDFs, KPaperFlux overlays transparent signatures on original vector documents, preserving 1:1 text quality and minimal file size.
*   **Chain of Trust:** Hybrid PDFs automatically embed the original digitally signed source document as an attachment for legal validity.

### 🤖 Agent-Based Workflows
*   **Playbooks:** Process documents through custom-defined state machines (e.g., `VERIFIED` → `TO_PAY` → `ARCHIVED`).
*   **Automation:** Intelligent routing based on AI-evaluated metadata.

### 📊 Advanced Reporting & Dynamic Dashboards
*   **Dynamic Analytics:** Real-time generation of charts (Bar, Pie, Line) based on your entire document corpus.
*   **Intelligent Visualization:** Pie charts with automatic "Others" grouping, side legends with elision, and pattern-based color distinction for maximum readability.
*   **Relative Date Filtering:** Predefined smart filters (Today, YTD, Last 90 Days) that stay dynamic as time passes.
*   **Global Zooming:** Visual consistency from 50% to 300% zoom across all report elements.

### 📦 Multi-Format Data Export
*   **Structured Data:** Export report results to CSV for external spreadsheet analysis.
*   **Document Archives:** One-click ZIP export of all original PDF source documents associated with a specific report.
*   **Hybrid PDF Reports:** (In Progress) Exporting visual reports as PDFs with embedded semantic metadata.

---

## 🏗️ Status & Development
*   **Current State:** Active development. High-stability core with rapidly evolving reporting and export capabilities.
*   **Reporting:** Feature-complete dynamic dashboard engine with multi-format export.
*   **GUI:** Solid desktop experience; optimized for high-density information displays.
*   **Standardization:** Strict adherence to European invoicing standards (EN 16931).

---

## 🚀 Installation & Quick Start

1.  **Clone:** `git clone https://github.com/schnebeck/KPaperFlux.git`
2.  **Env:** `python3 -m venv venv && source venv/bin/activate`
3.  **Install:** `pip install -r requirements.txt`
4.  **Hardware:** `sudo apt install sane-airscan` (Recommended for network scanners).
5.  **API Key:** Provide a Google Gemini API Key in `~/.config/kpaperflux/KPaperFlux.conf`.

---

## 🤝 Contribution & License

KPaperFlux follows strict **Clean Code** and **TDD** principles. Details can be found in the `devel/` folder.

**License:** GNU General Public License v3.0  
*(c) 2025-2026 Thorsten Schnebeck & The Antigravity Team*
