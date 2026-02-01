# KPaperFlux: Strategische Auswertung & Reporting-Konzept
**Datum:** 01.02.2026
**Status:** Planung / Architektur-Review (Post-Refactoring v2.0)

## 1. Status Quo: Das modernisierte Fundament

Nach dem erfolgreichen Refactoring steht KPaperFlux auf einer neuen technologischen Stufe. Die wesentlichen Errungenschaften sind:

*   **Schema-lose Metadaten (JSON-First):** Die Abkehr von starren SQL-Spalten (`doc_date`, `sender`, `amount`) hin zu einem dynamischen `semantic_data`-JSON-Block ermöglicht die Erfassung beliebig tiefer Informationen ohne Datenbank-Migrationen.
*   **KI-Robustheit:** Implementierung einer "Self-Correction"-Logik (Logical Retries mit Prompt-Strengthening). Die KI lernt aus JSON-Syntaxfehlern und korrigiert sich selbst.
*   **Effiziente Pipeline:** 
    *   **Stage 1.5 (Visual Audit):** Konzentration auf Forensik (Stempel, Unterschriften, Integrität).
    *   **Stage 2 (Semantik):** Vollständige Extraktion von Finanzdaten und Textreparatur über alle Seiten.
*   **Stabile UI:** Alle Komponenten (Listenansicht, Metadaten-Editor, Duplikat-Check) wurden erfolgreich auf die neue Architektur synchronisiert.

---

## 2. Die Vision: Vom Datengrab zum Wissensmanager

Das Ziel ist es nun, den "Schatz" der extrahierten Daten zu heben. Reporting ist hierbei nicht nur eine Liste, sondern eine **Interpretierebene**.

### A. Financial Intelligence & Reporting (Pflicht)
*   **Finanz-Zentrale:** Aggregation der `amount`-Werte über Zeiträume.
*   **Steuer-Vorbereitung:** Automatisierter Export (CSV/ZIP) für den Steuerberater, gruppiert nach Kategorien und Steuersätzen.
*   **Ausgaben-Dashboard:** Visualisierung von Cash-Flow und Burn-Rates (z.B. "Software-Abos", "Versicherungen").

### B. Prozess-Management & Workflow (Dynamik)
*   **Inbox Zero:** Nutzung der Status-Zustände (`NEW`, `PAID`, `TO_PAY`) zur Steuerung des Papierkrams.
*   **Fälligkeits-Überwachung:** Automatische Berechnung von Due-Dates (Belegdatum + n Tage) mit visuellen Warnsignalen (Ampelsystem) im UI.

### C. Kontext & Relationen (Wissen)
*   **Knowledge Graph:** Verknüpfung von Dokumenten (z.B. Angebot <-> Rechnung).
*   **Timeline View:** Anzeige der Dokumente auf einer chronologischen Achse statt in einer starren Liste.

---

## 3. Technische Säulen der `core/reporting.py`

Die Umsetzung erfolgt nach modernen Software-Design-Patterns, um Skalierbarkeit und Wartbarkeit zu garantieren.

### I. Stream-basierte Verarbeitung
Anstatt Daten im RAM zu sammeln, arbeiten wir mit Datei-Streams.
*   **Vorteil:** Export von tausenden Dokumenten bei minimalem Speicherverbrauch.
*   **Technik:** Manuelle JSON/CSV-Stream-Konstruktion direkt ins Datei-Handle.

### II. Strategy Pattern (Exporter)
Die Entkoppelung von Datenquelle und Export-Format.
*   `CsvExporter`, `JsonExporter`, `ExcelFriendlyExporter` (mit `utf-8-sig`).

### III. Aggregations-Layer (Finanzen & Zeitreihen)
Ein spezielles Modul im Core berechnet Summen und Gruppen.
*   **Input:** Filter-Ergebnis der Datenbank.
*   **Output:** Aggregierte Datenstrukturen für Charts und Reports.

### IV. Data Quality Scoring
Ein "Wachhund"-Modul bewertet die Gesundheit der Daten (Anomalie-Erkennung).
*   **Check:** Fehlende Pflichtfelder, falsche Datumsformate, ungewöhnliche Beträge (im Vergleich zum Absender-Durchschnitt).

---

## 4. Umsetzungsstrategie (Phasenmodell)

### Phase 1: Die Reporting-Engine (Core)
*   Implementierung der Basis-Klasse `ReportGenerator`.
*   Erstellung des `FinancialTimeModule` zur Aggregation von Beträgen nach Monaten/Tags.
*   Integration des `CsvExporter` mit Excel-Optimierung (`utf-8-sig`).

### Phase 2: Actionability (Quick Wins)
*   **GiroCode Generator:** Integration eines QR-Code-Generators (EPC-Standard), basierend auf extrahierten IBAN/Betrag-Daten von Stage 2.
*   **Dashboard-Integration:** Erste grafische Auswertungen im Hauptfenster (Balkendiagramme für Ausgaben).

### Phase 3: Workflow & Quality
*   Einführung des **Anomalie-Checkers** (Warnung bei Preisabweichungen).
*   Implementierung des **Smart Folder Export** (Physikalische Sortierung auf HDD basierend auf Metadaten).

---

## 5. Fazit
KPaperFlux wechselt nun von der Phase der **Datenerfassung** in die Phase der **Datennutzung**. Die architektonische Entscheidung für JSON-Metadaten erweist sich hierbei als der entscheidende Beschleuniger, da komplexe Reports flexibel auf der `semantic_data` Schicht operieren können.
