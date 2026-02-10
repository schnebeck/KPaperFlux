<div align="center">
  <img src="resources/icon.png" alt="KPaperFlux Logo" width="128" height="128">
  <h1 align="center">KPaperFlux</h1>
  <p align="center">
    <strong>Dokumenten-Management-System mit KI-gestützter semantischer Analyse</strong><br>
    <em>Implementiert in Python/Qt6 unter Nutzung der Google Gemini API</em>
  </p>
</div>

---

## Funktionsübersicht

KPaperFlux ist ein Werkzeug zur Erfassung, Strukturierung und Archivierung von Dokumenten. Der Fokus liegt auf der automatisierten Extraktion von Metadaten und der technischen Aufbereitung von PDF-Dokumenten.

### 1. Analyse-Pipeline
Die Verarbeitung erfolgt in mehreren aufeinanderfolgenden Stufen:
*   **Klassifizierung (Stage 1):** Identifikation des Dokumententyps und Bestimmung der logischen Grenzen (Seitenbereiche) bei Multi-Dokument-Scans.
*   **Visuelle Analyse (Stage 1.5):** Detektion und separate Extraktion von Bildelementen wie Stempeln, Unterschriften oder handschriftlichen Vermerken.
*   **Semantische Extraktion (Stage 2):** Überführung der Textinhalte in strukturierte JSON-Daten gemäß EN 16931 (ZUGFeRD 2.2). Dies umfasst Absender- und Empfängerdaten, Rechnungsdaten und Positionslisten.
*   **Validierung:** Mathematische Prüfung von Netto-, Steuer- und Bruttobeträgen sowie die Normalisierung von Bankdaten (IBAN/BIC).

### 2. PDF-Verarbeitung und Rendering
*   **Hybrid-PDF Architektur:** Verfahren zur verlustfreien Zusammenführung von digitalen Originalen und analogen Ergänzungen. Unterschriften oder Stempel werden als transparente Ebenen über das Vektordokument gelegt, um die Textqualität und Durchsuchbarkeit zu erhalten.
*   **Automatisierte PDF-Generierung:** Rekonstruktion von semantischen Daten in DIN 5008 konforme PDF-Dokumente mittels ReportLab/Platypus.
    *   Dynamische Spaltenbreitenberechnung basierend auf der Inhaltslänge.
    *   Automatisierte Paginierung mit wiederkehrenden Kopfzeilen und Seitenzählern.
    *   Unterstützung für Finanzdokumente und technische Zertifikate (RoHS, REACH).

### 3. Workflow-Steuerung
*   **Playbook-System:** Definition von Verarbeitungszuständen (z.B. `NEW`, `VERIFIED`, `PAID`) und Übergangsregeln.
*   **Zustandsverwaltung:** Dokumente können basierend auf Extraktionsergebnissen oder manueller Prüfung unterschiedliche Workflows durchlaufen.

### 4. Integration und Formate
*   **ZUGFeRD / Factur-X:** Extraktion eingebetteter XML-Metadaten aus PDF/A-Rechnungen.
*   **GiroCode:** Generierung von EPC-QR-Codes aus extrahierten Zahlungsdaten.
*   **Export:** CSV-Schnittstelle (Excel-optimiert) zur Weiterverarbeitung in Buchhaltungssystemen.

---

## Technische Details

*   **Programmiersprache:** Python 3.12+
*   **UI-Framework:** PyQt6
*   **PDF-Bibliothek:** PyMuPDF (fitz)
*   **Datenhaltung:** SQLite
*   **KI-Schnittstelle:** Google GenAI (Gemini Flash/Pro Modelle)

---

## Installation

### Voraussetzungen
*   **Betriebssystem:** Linux
*   **Abhängigkeiten:** `sane-airscan` für Netzwerk-Scanner-Unterstützung.
*   **Schnittstellen:** Google AI Studio API-Key für die semantische Analyse.

### Setup
1. Repository klonen.
2. Virtuelle Umgebung erstellen (`python3 -m venv venv`).
3. Abhängigkeiten installieren (`pip install -r requirements.txt`).
4. Konfiguration in `~/.config/kpaperflux/KPaperFlux.conf` hinterlegen.

---

## Lizenz

Dieses Projekt ist unter der **GNU General Public License v3.0** lizenziert.
