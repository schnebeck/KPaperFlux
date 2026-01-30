# KPaperFlux 🚀
> **Next-Generation Hybrid Document Management System for Linux**  
> *Powered by Google Gemini 2.0 Flash & Python/Qt6*

![Status](https://img.shields.io/badge/Status-Active_Development-green)
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-purple)

**KPaperFlux** ist nicht einfach nur ein weiteres DMS. Es ist ein intelligenter **Dokumenten-Veredler**. Anstatt Dokumente nur abzulegen, versteht, repariert und strukturiert KPaperFlux den Inhalt mithilfe modernster KI.

Es wurde speziell für **Power-User** und **Linux-Enthusiasten** entwickelt, die maximale Kontrolle über ihre Daten haben wollen, aber nicht auf den Komfort von Cloud-KI verzichten möchten.

---

## 🔥 Key Features

### 🧠 Adaptive AI Pipeline (The "Brain")
KPaperFlux nutzt eine mehrstufige, intelligente Analyse-Pipeline, um Dokumente zu verstehen:
*   **Stage 1 - Der "Pre-Flight":** Entscheidet in Millisekunden, ob es sich um ein Buch, eine Rechnung oder einen Stapel Dokumente handelt.
*   **Stage 1.5 - Visual Auditor (X-Ray Mode):** Ein forensisches Modul, das Stempel, Notizen und Unterschriften visuell vom Originaltext trennt.
    *   *Feature:* Erkennt handschriftliche "Bezahlt"-Vermerke oder Kontierungsstempel und extrahiert deren Daten separat.
*   **Stage 2 - Semantische Extraktion:** Extrahiert strukturierte JSON-Daten (Sender, Datum, Line Items) mit einem Schema, das selbst DigiKey-Rechnungen mit 50+ Positionen versteht.

### ⚡ Performance & Token-Effizienz
*   **Sandwich-Mode:** Bei großen Handbüchern werden nur Anfang und Ende gescannt, um KI-Kosten zu sparen.
*   **Header-Scan:** Bei Dokumentenstapeln analysiert das System nur die Kopfbereiche.
*   **Flash-Optimierung:** Nutzt dynamisch das 1M Context Window von Gemini 2.x für komplexe Analysen.

### 🛡️ Hybrid Workflow
*   **SANE Integration:** Direkte Ansteuerung von Scannern unter Linux.
*   **Drag & Drop:** Einfaches Importieren von PDFs.
*   **Metadata Editor:** Ein mächtiger Editor, um die KI-Ergebnisse zu verifizieren und zu korrigieren.

---

## 🛠️ Technologie-Stack

*   **Core:** Python 3.12+
*   **GUI:** PyQt6 (Modernes, responsives Interface)
*   **AI Engine:** Google Generative AI (Gemini 2.0/2.5 Flash)
*   **PDF Engine:** PyMuPDF (fitz) für rasend schnelles Rendering
*   **Database:** SQLite (lokal, schnell, serverless)

---

## 🚀 Installation & Setup

### Voraussetzungen
*   Linux (getestet auf Ubuntu/Debian/Fedora)
*   Python 3.10 oder höher
*   Ein Google AI Studio API Key (Kostenlos verfügbar)

### Quick Start

```bash
# 1. Repository klonen
git clone https://github.com/schnebeck/KPaperFlux.git
cd KPaperFlux

# 2. Virtuelle Umgebung erstellen
python3 -m venv venv
source venv/bin/activate

# 3. Abhängigkeiten installieren
pip install -r requirements.txt
```

### Konfiguration
Erstelle die Datei `~/.config/kpaperflux/KPaperFlux.conf`:

```ini
[General]
debug_mode=true

[AI]
api_key=DEIN_GEMINI_API_KEY_HIER
gemini_model=gemini-2.5-flash
```

---

## 📚 Entwicklung

KPaperFlux folgt strengen **Clean Code** und **TDD** (Test Driven Development) Prinzipien.
Entwickler finden detaillierte Dokumentation im Ordner `devel/`:

*   `Agenten-Framework.md`: Unsere Philosophie für AI-gestützte Entwicklung.
*   `TDD_Strategie_KPaperFlux.md`: Wie wir testen (PyTest, Mocks).

---

## 🤝 Contributing

Contributions sind willkommen! Bitte erstelle Issues für Bugs oder Feature-Requests.

---

*(c) 2025-2026 Thorsten Schnebeck & The Antigravity Agent Team*
