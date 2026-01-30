<div align="center">
  <img src="resources/icon.png" alt="KPaperFlux Logo" width="128" height="128">
  <h1 align="center">KPaperFlux</h1>
  <p align="center">
    <strong>Next-Generation Hybrid Document Management System for Linux</strong><br>
    <em>Powered by Google Gemini 2.5 Flash & Python/Qt6</em>
  </p>
  <p align="center">
    <a href="LICENSE">
      <img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3">
    </a>
    <img src="https://img.shields.io/badge/Status-Active_Development-green" alt="Status">
    <img src="https://img.shields.io/badge/Python-3.10+-blue" alt="Python">
  </p>
</div>

**KPaperFlux** is not just another DMS. It is an intelligent **document refiner**. Instead of simply archiving documents, KPaperFlux understands, repairs, and structures content using state-of-the-art AI.

Designed specifically for **Power Users** and **Linux Enthusiasts** who demand maximum control over their data without sacrificing the convenience of cloud AI.

---

## 🔥 Key Features

### 🧠 Adaptive AI Pipeline (The "Brain")
KPaperFlux employs a multi-stage, intelligent analysis pipeline to understand documents:
*   **Stage 1 - "Pre-Flight":** Decides in milliseconds whether the input is a book, an invoice, or a stack of documents.
*   **Stage 1.5 - Visual Auditor (X-Ray Mode):** A forensic module that visually separates stamps, notes, and signatures from the original text.
    *   *Feature:* Detects handwritten "Paid" notes or accounting stamps and extracts their data separately.
*   **Stage 2 - Semantic Extraction:** Extracts structured JSON data (Sender, Date, Line Items) using a schema capable of understanding complex documents like DigiKey invoices with 50+ line items.

### ⚡ Performance & Token Efficiency
*   **Sandwich Mode:** For large manuals, only the start and end are scanned to save AI costs.
*   **Header Scan:** For document stacks, the system analyzes only the header regions.
*   **Flash Optimization:** Dynamically leverages the 1M Context Window of Gemini 2.x for complex analyses.

### 🛡️ Hybrid Workflow
*   **SANE Integration:** Direct control of scanners under Linux.
*   **Drag & Drop:** Easy import of PDF files.
*   **Metadata Editor:** A powerful editor to verify and correct AI results.

---

## 🛠️ Technology Stack

*   **Core:** Python 3.12+
*   **GUI:** PyQt6 (Modern, responsive interface)
*   **AI Engine:** Google Generative AI (Gemini 2.5 Flash)
*   **PDF Engine:** PyMuPDF (fitz) for high-performance rendering
*   **Database:** SQLite (local, fast, serverless)

---

## 🚀 Installation & Setup

### Requirements
*   **OS:** Linux (tested on Ubuntu/Debian/Fedora/Arch)
*   **Python:** 3.10 or higher
*   **Scanner Drivers:** For modern network scanners (AirPrint/eSCL/WSD), we strongly recommend **`sane-airscan`**.
    *   *Ubuntu/Debian:* `sudo apt install sane-airscan`
    *   *Fedora:* `sudo dnf install sane-airscan`
*   **AI Access:** A Google AI Studio API Key.

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/schnebeck/KPaperFlux.git
cd KPaperFlux

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### 🔑 Getting your API Key
KPaperFlux requires a Google Gemini API Key. The "Free Tier" is sufficient for personal use.
1.  Visit [Google AI Studio](https://aistudio.google.com/app/apikey).
2.  Log in with your Google Account.
3.  Click **"Create API key"** (Create key in new project).
4.  Copy the key string (starts with `AIza...`).

### Configuration
Create the file `~/.config/kpaperflux/KPaperFlux.conf`:

```ini
[General]
debug_mode=true

[AI]
api_key=YOUR_GEMINI_API_KEY_HERE
gemini_model=gemini-2.5-flash
```

---

## 📚 Development

KPaperFlux follows strict **Clean Code** and **TDD** (Test Driven Development) principles.
Developers can find detailed documentation in the `devel/` folder:

*   `Agenten-Framework.md`: Our philosophy for AI-assisted development.
*   `TDD_Strategie_KPaperFlux.md`: How we test (PyTest, Mocks).

---

## 🤝 Contributing

Contributions are welcome! Please create issues for bugs or feature requests.

---

*(c) 2025-2026 Thorsten Schnebeck & The Antigravity Agent Team*

## License

This project is licensed under the terms of the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.
