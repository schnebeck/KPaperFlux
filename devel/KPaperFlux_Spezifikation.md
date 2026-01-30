# **Projektdefinition: KPaperFlux**

Version: 1.0  
Zielplattform: Linux (KDE Plasma)  
Kerntechnologie: Python, Qt6, SQLite, Google Gemini AI

## **1\. Projektvision & Architektur**

**KPaperFlux** ist eine native Desktop-Anwendung für intelligentes Dokumentenmanagement (DMS) unter KDE Plasma. Sie kombiniert lokale High-Performance-Verarbeitung mit KI-gestützter Analyse.

### **1.1 Architektur-Entscheidung**

* **Typ:** Native "Thick Client" Desktop App.  
* **Begründung:** Direkter Hardware-Zugriff (Scanner/ADF), Nutzung lokaler Rechenleistung für Bildverarbeitung (600 DPI \-\> 150 DPI), Integration in den Desktop-Workflow.  
* **Storage-Konzept:** "Managed Vault". Der User sieht nur die UI, nicht die Ordnerstruktur. Die Datenintegrität hat oberste Priorität.

## **2\. Technologie-Stack**

| Komponente | Technologie / Bibliothek | Zweck |
| :---- | :---- | :---- |
| **Sprache** | Python 3.10+ | Hauptlogik |
| **GUI** | PyQt6 | Benutzeroberfläche, native KDE-Optik |
| **Datenbank** | SQLite | Speicherung von Metadaten, Tags, OCR-Text |
| **Scanner** | python-sane | Ansteuerung von Scannern (SANE Backend) |
| **OCR & PDF** | OCRmyPDF, ghostscript | Texterkennung, PDF/A Konvertierung |
| **Bildverarbeitung** | scikit-image, unpaper | Deskewing, Despeckling (Reinigung) |
| **KI / Intelligenz** | Google Gemini API | Semantische Klassifizierung, Daten-Extraktion |

## **3\. Funktionale Anforderungen**

### **3.1 Die Pipeline (Der "Flux")**

Jedes Dokument durchläuft beim Import diese Schritte:

1. **Input:** Scan (600 DPI) oder PDF-Import.  
2. **Preprocessing:** Automatische Rotation (Deskew) und Bereinigung (Despeckle) auf Rohdaten via Plugin-System.  
3. **OCR:** Texterkennung via Tesseract (unsichtbarer Text-Layer).  
4. **KI-Analyse:** Google Gemini extrahiert Datum, Betrag, Typ und prüft Logik (z.B. "Adress-Check").  
5. **Archivierung:** Downsampling auf 150 DPI (JBIG2 Kompression) und Speicherung als PDF/A.

### **3.2 Storage (Der "Vault")**

* **Immutability:** Originaldateien werden nach dem Schreiben nie verändert.  
* **Naming:** Dateinamen im System sind UUIDs, echte Namen nur in der DB.  
* **Duplikat-Check:** Abgleich mittels pHash (visuell) und Fuzzy-Text-Suche vor dem Speichern.

### **3.3 GUI & Reporting**

* **Suche:** Facetten-Suche (Jahr, Tag, Typ), Visual Query Builder und Volltextsuche.  
* **Reporting:** Dynamisches Hinzufügen von Stempeln ("Privatkauf", "Gebucht") als Overlay beim Export/Druck. Das Original bleibt unberührt.

## **4\. Datenmodell (SQLite Schema)**

CREATE TABLE documents (  
    id INTEGER PRIMARY KEY AUTOINCREMENT,  
    uuid TEXT UNIQUE NOT NULL,  
    original\_filename TEXT,  
      
    \-- KI & Metadaten  
    doc\_date DATE,  
    sender TEXT,  
    amount DECIMAL(10, 2),  
    doc\_type TEXT,   \-- "Rechnung", "Vertrag"  
      
    \-- Duplikat-Fingerprints  
    phash TEXT,  
    text\_content TEXT,  
      
    created\_at DATETIME DEFAULT CURRENT\_TIMESTAMP  
);

CREATE TABLE overlays (  
    doc\_id INTEGER,  
    overlay\_type TEXT,  \-- "STAMP", "TEXT"  
    content TEXT,       \-- "PRIVATKAUF"  
    position\_x INTEGER,  
    position\_y INTEGER,  
    FOREIGN KEY(doc\_id) REFERENCES documents(id)  
);  
