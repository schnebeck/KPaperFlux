<div align="center">
  <img src="resources/icon.png" alt="KPaperFlux Logo" width="128" height="128">
  <h1 align="center">KPaperFlux</h1>
  <p align="center">
    <strong>Personal Document Management with Forensic AI & Semantic Precision</strong><br>
    <em>A Python/Qt6 Desktop Platform powered by Google Gemini</em>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/Status-Active_Development-green" alt="Status">
    <img src="https://img.shields.io/badge/Python-3.12+-blue" alt="Python">
    <img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3">
  </p>
</div>

> [!WARNING]
> **PRE-RELEASE SOFTWARE:** KPaperFlux is currently in a state of rapid, high-volatility development ("wild development phase"). Breaking changes are common. **Use with real, sensitive data at your own risk!** Always keep backups of your documents.

---

## 🛠️ The Philosophy

KPaperFlux is more than a storage tool; it is a **Document Refiner**. It extracts the semantic "Digital Twin" from your paperwork. While other systems focus on full-text search, KPaperFlux focuses on **understanding**: converting pixels and text into structured, mathematically validated data.

Designed for users who demand **forensic accuracy** and **privacy-first local management**, without sacrificing the power of large language models.

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

---

## 🏗️ Status & Development
*   **Current State:** Active high-volatility development.
*   **GUI:** Relatively solid captured/audit interface, though console output (stdout) is still used for deep debugging.
*   **Translation:** German support is growing; core systems are built for multi-language semantic parsing.

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
