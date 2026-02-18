"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           fill_l10n.py
Description:    Orchestration script for batch-populating translations into
                the .ts file using L10nTool. Serves as the central mapping
                authority for German UI strings.
Documentation:  See devel/agent_framework.md (Section 5)
------------------------------------------------------------------------------
"""

import sys
from pathlib import Path
from l10n_tool import L10nTool

def fill():
    ts_path = "../resources/l10n/de/gui_strings.ts"
    tool = L10nTool(ts_path)
    
    common = {
        "&File": "&Datei",
        "&Edit": "&Bearbeiten",
        "&View": "&Ansicht",
        "&Tools": "Werk&zeuge",
        "&Help": "&Hilfe",
        "&Debug": "Debu&g",
        "&Config": "&Konfiguration",
        "&Settings...": "&Einstellungen...",
        "Close": "Schließen",
        "Save": "Speichern",
        "Cancel": "Abbrechen",
        "Delete": "Löschen",
        "Add": "Hinzufügen",
        "Edit": "Bearbeiten",
        "Error": "Fehler",
        "Warning": "Warnung",
        "Info": "Info",
        "Confirm": "Bestätigen",
        "Success": "Erfolg",
        "Search": "Suchen",
        "Search:": "Suche:",
        "Filter:": "Filter:",
        "Tags:": "Tags:",
        "Status:": "Status:",
        "Date:": "Datum:",
        "Ready": "Bereit",
        "Archived": "Archiviert",
        "General": "Allgemein",
        "History": "Historie",
        "Comment": "Kommentar",
        "User": "Benutzer",
        "Time": "Zeit",
        "Action": "Aktion",
        "Value": "Wert",
        "Field": "Feld",
        "Section": "Kategorie",
        "Unknown": "Unbekannt",
        "Private": "Privat",
        "Business": "Geschäftlich",
        "Inbound": "Eingang",
        "Outbound": "Ausgang",
        "Internal": "Intern",
        "Type": "Typ",
        "Text": "Text",
        "Page": "Seite",
        "Confidence": "Konfidenz",
        "Recipient:": "Empfänger:",
        "Amount:": "Betrag:",
        "Purpose:": "Verwendungszweck:",
        "UUID:": "UUID:",
        "Pages:": "Seiten:",
        "Created At:": "Erstellt am:",
        "Export Name:": "Exportname:",
        "Storage Location:": "Lagerort:",
        "Document Date:": "Belegdatum:",
        "Sender:": "Absender:",
        "Fit": "Einpassen",
        "Copied!": "Kopiert!",
        "Workflows": "Abläufe",
        "Dashboard": "Dashboard",
        "Reports": "Berichte",
        "Cockpit": "Cockpit",
        "Documents": "Dokumente",
        "Settings": "Einstellungen",
        "Browse...": "Durchsuchen...",
        "Export": "Exportieren",
        "OK": "OK",
        "Add Row": "Zeile hinzufügen",
        "Remove Row": "Zeile entfernen",
        "Save / Apply": "Speichern / Anwenden",
        "Locked (Immutable)": "Gesperrt (Unveränderbar)",
        "Analysis": "Analyse",
        "Payment": "Zahlung",
        "Stamps": "Stempel",
        "Semantic Data": "Semantische Daten",
        "Source Mapping": "Quellen",
        "Debug Data": "Debug-Daten",
        "Save Changes": "Änderungen speichern",
        "Title:": "Titel:",
        "Mode:": "Modus:",
        "Color:": "Farbe:",
        "New Title:": "Neuer Titel:",
        "Rename": "Umbenennen",
        "Result": "Ergebnis",
        "Merge": "Zusammenführen",
        "New Name:": "Neuer Name:",
    }

    # Context-specific overrides or additions
    contexts = {
        "MainWindow": {
            "Workflows": "Abläufe",
            "Reports": "Berichte",
            "Cockpit": "Cockpit",
            "Documents": "Dokumente",
            "&Import Document": "Dokument &importieren",
            "Import from Transfer": "Aus Transfer importieren",
            "&Scan...": "&Scannen...",
            "&Print": "Dr&ucken",
            "&Delete Selected": "Auswahl &löschen",
            "Export shown List...": "Liste exportieren...",
            "E&xit": "&Beenden",
            "&Refresh List": "Liste &neu laden",
            "Show Extra Data": "Extra-Daten anzeigen",
            "Filter Panel": "Filter-&Panel",
            "&Maintenance": "&Wartung",
            "Check Integrity (Orphans/Ghosts)": "Integrität prüfen (Waisen/Geister)",
            "Find Duplicates": "Duplikate finden",
            "Manage Tags": "Tags verwalten",
            "Purge All Data (Reset)": "Alle Daten löschen (Reset)",
            "External Plugins": "Externe Plugins",
            "&Debug": "Debu&g",
            "Show Orphaned Vault Files": "Verwaiste Vault-Dateien zeigen",
            "Prune Orphaned Vault Files (Console)": "Verwaiste Vault-Dateien bereinigen",
            "Show Broken Entity References": "Defekte Entity-Referenzen zeigen",
            "Prune Broken Entity References (Console)": "Defekte Entity-Referenzen bereinigen",
            "Deduplicate Vault (Inhaltsbasiert)": "Vault deduplizieren (Inhalt)",
            "&Config": "&Konfiguration",
            "&Settings...": "&Einstellungen...",
            "&Semantic Data": "&Semantische Daten",
            "List Missing": "Fehlende auflisten",
            "List Mismatched": "Abweichungen auflisten",
            "Run Extraction (Selected)": "Extraktion starten (Auswahl)",
            "Process empty Documents": "Leere Dokumente verarbeiten",
            "&Help": "&Hilfe",
            "&About": "&Über",
            "Docs: %s/%s": "Doks: %s/%s",
            "AI: %s": "KI: %s",
            "Edit Document...": "Dokument bearbeiten...",
            "Merge Selected Documents": "Auswahl zusammenführen",
        },
        "MetadataEditorWidget": {
            "Locked (Immutable)": "Gesperrt (Unveränderbar)",
            "🔍 Audit": "🔍 Prüfung",
            "Eligible for PKV Reimbursement": "PKV-relevant",
            "Document Types:": "Dokumenttypen:",
            "Tenant Context:": "Mandantenkontext:",
            "--- Extracted Data ---": "--- Extrahierte Daten ---",
            "Analysis": "Analyse",
            "Payment": "Zahlung",
            "Stamps": "Stempel",
            "Semantic Data": "Semantische Daten",
            "Source Mapping": "Quellen",
            "Debug Data": "Debug-Daten",
            "Save Changes": "Änderungen speichern",
            "Add Entry": "Eintrag hinzufügen",
            "Remove Selected": "Auswahl entfernen",
            "GiroCode (EPC)": "GiroCode (EPC)",
            "Standardized QR code for SEPA transfers (EPC-QR).": "Standardiesierter QR-Code für SEPA-Überweisungen.",
            "Copy Payload": "Daten kopieren",
            "Copy the raw GiroCode data for banking apps": "Raw-GiroCode-Daten kopieren",
        },
        "PdfViewerWidget": {
            "Split Document": "Dokument teilen",
            "Save Changes": "Änderungen speichern",
            "Fit": "Einpassen",
            "Copied!": "Kopiert!",
            "Close": "Schließen",
            "Link scroll and zoom": "Scrollen und Zoom koppeln",
            "Show visual differences": "Unterschiede zeigen",
        },
        "AdvancedFilterWidget": {
            "Advanced Filter \u25BC": "Erweiterter Filter \u25BC",
            "Rules...": "Regeln...",
            "Advanced Criteria": "Erweiterte Kriterien",
            "From:": "Von:",
            "Enable Date": "Datum aktivieren",
            "To:": "Bis:",
            "Type:": "Typ:",
            "All": "Alle",
            "Tags:": "Tags:",
            "e.g. tax": "z.B. Steuer",
            "Filter anwenden": "Filter anwenden",
            "Searching...": "Suche...",
            "in all documents": "in allen Dokumenten",
            "in current view": "in aktueller Ansicht",
            "--- Saved Filter ---": "--- Gesp. Filter ---",
            "Browse All...": "Alle durchsuchen...",
            "Save Filter": "Filter speichern",
            "No conditions to save.": "Keine Bedingungen zum Speichern.",
            "Export Filter": "Filter exportieren",
            "No conditions to export.": "Keine Bedingungen zum Exportieren.",
            "Export Successful": "Export erfolgreich",
            "Filter exported to %s": "Filter exportiert nach %s",
            "Filter Imported": "Filter importiert",
            "Loaded filter: %s": "Filter geladen: %s",
            "Import Failed": "Import fehlgeschlagen",
            "File is of type '%s', expected 'smart_list'.": "Datei ist Typ '%s', erwartet 'smart_list'.",
            "Delete Filter": "Filter löschen",
            "Are you sure you want to delete '%s'?": "Sicher, dass '%s' gelöscht werden soll?",
            "e.g. Amazon 2024 Invoice...": "z.B. Amazon 2024 Rechnung...",
            "Create View-filter": "Ansichtsfilter erstellen",
            "Rule applied. %d documents modified.": "Regel angewendet. %d Dokumente geändert.",
            "If checked, combines the search with the active filters from 'Filter View'.": "Wenn aktiviert, wird die Suche mit den aktiven Filtern der Ansicht kombiniert.",
            "Select:": "Auswahl:",
            "Rev.": "Verw.",
            "Revert": "Verwerfen",
            "Save...": "Speichern...",
            "Manage": "Verwalten",
            "Enter tags to add. Press comma or Enter to confirm (e.g. INVOICE, TELEKOM)": "Tags zum Hinzufügen. Komma oder Enter zum Bestätigen.",
            "Enter tags to remove. Press comma or Enter to confirm (e.g. DRAFT, REVIEW)": "Tags zum Entfernen. Komma oder Enter zum Bestätigen.",
            "Create a search-view that filters for the tags this rule adds": "Erstellt eine Ansicht, die nach den Tags dieser Regel filtert",
            "Apply to View": "Auf Ansicht anwenden",
            "Apply to all": "Auf alle anwenden",
            "Automatically apply this rule to new documents during import/analysis": "Diese Regel automatisch bei Import/Analyse auf neue Dokumente anwenden",
        },
        "ReportingWidget": {
            "Select Report:": "Bericht wählen:",
            "Add Comment": "Kommentar hinzufügen",
            "New Report": "Neuer Bericht",
            "Import from PDF": "Aus PDF importieren",
            "Clear": "Leeren",
            "Save Layout": "Layout speichern",
            "Load Layout": "Layout laden",
            "Fit": "Einpassen",
            "Export Data": "Daten exportieren",
            "Export as CSV (Data)": "Als CSV exportieren (Daten)",
            "Export as PDF (Report)": "Als PDF exportieren (Bericht)",
            "Export as ZIP (Documents)": "Als ZIP exportieren (Dokumente)",
            "Bar Chart": "Balkendiagramm",
            "Vendor Distribution": "Verteilung nach Lieferant",
            "Trend Analysis": "Trendanalyse",
            "Detailed Data": "Detaildaten",
        },
        "BatchTagDialog": {
            "Batch Tag Editor": "Massen-Tag-Editor",
            "Logic": "Logik",
            "Common Tags:": "Gemeinsame Tags:",
            "Force Remove Mixed:": "Gemischte entfernen:",
            "<b>Checked Tags:</b> Will be present on ALL selected documents (Merged).<br><b>Unchecked Tags:</b> Will be REMOVED from ALL selected documents (if they were common).<br><i>Individual unique tags on specific documents are preserved unless forced removed.</i>": "<b>Aktivierte Tags:</b> Werden auf ALLEN gewählten Dokumenten gesetzt.<br><b>Deaktivierte Tags:</b> Werden von ALLEN gewählten Dokumenten ENTFERNT.<br><i>Individuelle Tags bleiben erhalten, sofern nicht 'Gemischte entfernen' aktiv ist.</i>",
        },
        "VocabularySettingsWidget": {
            "Document Types": "Dokumenttypen",
            "Approved Types": "Zugelassene Typen",
            "Aliases (Synonyms)": "Aliasse (Synonyme)",
            "Target Type": "Zieltyp",
            "Add Type": "Typ hinzufügen",
            "Add Alias": "Alias hinzufügen",
            "Select Target": "Ziel wählen",
            "Map to Type:": "Zuweisen zu Typ:",
            "Define types first.": "Zuerst Typen definieren.",
            "Define tags first.": "Zuerst Tags definieren.",
        },
        "DocumentListWidget": {
            "Merge Selected Documents": "Auswahl zusammenführen",
            "Edit Document...": "Dokument bearbeiten...",
            "Reprocess / Re-Analyze": "Neu verarbeiten",
            "Show generic Document": "Generisches Dokument anzeigen",
            "Extract from Selection": "Aus Auswahl extrahieren",
            "Extract from View": "Aus Ansicht extrahieren",
            "Manage Tags...": "Tags verwalten...",
            "Stamp...": "Stempeln...",
            "Apply Rule...": "Regel anwenden...",
            "Save as List...": "Als Liste speichern...",
            "Export Selected...": "Auswahl exportieren...",
            "Export All Visible...": "Alle sichtbaren exportieren...",
            "Restore": "Wiederherstellen",
            "Delete Permanently": "Endgültig löschen",
            "Delete Document": "Dokument löschen",
            "Digital Original (Signed)": "Digitales Original (Signiert)",
            "Digital Original (ZUGFeRD/Factur-X)": "Digitales Original (ZUGFeRD)",
            "Digital Original (Signed & ZUGFeRD)": "Digitales Original (Signiert & ZUGFeRD)",
            "Hybrid Container (KPaperFlux Protected)": "Hybrid-Container (KPaperFlux)",
            "Trash Bin": "Mülleimer",
        },
        "SettingsDialog": {
            "Settings": "Einstellungen",
            "General": "Allgemein",
            "Vocabulary": "Vokabular",
            "Identity": "Identität",
            "Logging": "Logging",
            "AI Backend:": "KI-Backend:",
            "Gemini API Key:": "Gemini API-Schlüssel:",
            "Ollama URL:": "Ollama URL:",
            "OpenAI API Key:": "OpenAI API-Schlüssel:",
            "Anthropic API Key:": "Anthropic API-Schlüssel:",
        },
        "CockpitEntryDialog": {
            "Cockpit View Configuration": "Dashboard-Kachel Konfiguration",
            "Display Title:": "Anzeigename:",
            "e.g. My Invoices": "z.B. Meine Rechnungen",
            "Linked Filter Rule:": "Verknüpfte Filter-Regel:",
            "--- Choose Filter ---": "--- Filter wählen ---",
            "Inbox (NEW)": "Eingang (NEU)",
            "Total Documents": "Gesamt Dokumente",
            "Processed Documents": "Verarbeitete Dokumente",
            "Filter: %s": "Filter: %s",
            "Aggregation Mode:": "Berechnungs-Modus:",
            "Count documents": "Anzahl Dokumente",
            "Sum amounts (€)": "Summe Beträge (€)",
            "Color Theme:": "Farb-Thema:",
            "Choose Color...": "Farbe wählen...",
            "Save View": "Kachel speichern",
        },
        "CockpitWidget": {
            "Inbox": "Eingang",
            "Urgent": "Dringend",
            "Total Documents": "Gesamt Dokumente",
            "Total Invoiced": "Gesamt fakturiert",
            "Processed": "Verarbeitet",
            "Review": "Prüfung",
            "Rename View": "Kachel umbenennen",
        },
        "ColumnManagerDialog": {
            "Configure Columns": "Spalten konfigurieren",
            "Visible Columns": "Sichtbare Spalten",
            "Available Columns": "Verfügbare Spalten",
        },
        "DateRangePicker": {
            "Custom Range": "Benutzerdefiniert",
            "Today": "Heute",
            "Yesterday": "Gestern",
            "Last 7 Days": "Letzte 7 Tage",
            "Last 30 Days": "Letzte 30 Tage",
            "This Month": "Diesen Monat",
            "Last Month": "Letzten Monat",
            "Apply": "Anwenden",
        },
        "DuplicateFinderDialog": {
            "Find Duplicates": "Duplikate finden",
            "Scan for duplicates based on content hash or metadata.": "Nach Duplikaten suchen (Hash oder Metadaten).",
            "Identify by:": "Identifizieren durch:",
            "File Hash (Exact matches)": "Datei-Hash (Exakte Treffer)",
            "Metadata (Entity, Date, Amount)": "Metadaten (Entity, Datum, Betrag)",
            "Start Scan": "Suche starten",
            "Duplicates found: %d": "Duplikate gefunden: %d",
        },
        "TagManagerDialog": {
            "Tag Manager": "Tag-Manager",
            "Rename": "Umbenennen",
            "Merge Selected": "Auswahl zusammenführen",
            "Please select exactly one tag to rename.": "Bitte genau ein Tag zum Umbenennen wählen.",
            "Rename Tag": "Tag umbenennen",
            "Please select at least two tags to merge.": "Bitte mindestens zwei Tags zum Zusammenführen wählen.",
            "Merge Tags": "Tags zusammenführen",
            "Delete Tags": "Tags löschen",
        },
        "ViewManagerDialog": {
            "Delete this view?": "Diese Ansicht löschen?",
        },
        "WorkflowManagerWidget": {
            "Dashboard": "Dashboard",
            "Rule Editor": "Regel-Editor",
            "New Rule": "Neue Regel",
            "Revert": "Verwerfen",
            "Save Rule": "Regel speichern",
            "Manage...": "Verwalten...",
            "Create a new workflow rule": "Neue Workflow-Regel erstellen",
            "Discard unsaved changes": "Änderungen verwerfen",
            "Save and activate the current rule": "Aktive Regel speichern",
            "Manage rule files (delete, rename, import)": "Regel-Dateien verwalten",
            "INVOICE, TELEKOM, ...": "RECHNUNG, TELEKOM, ...",
            "Move State Up": "Zustand nach oben",
            "Move State Down": "Zustand nach unten",
            "Change display name only (ID remains fixed)": "Nur Anzeigename ändern (ID bleibt gleich)",
            "New Workflow": "Neuer Workflow",
            "Enter display name:": "Anzeigename eingeben:",
            "Duplicate Name": "Name bereits vergeben",
            "A workflow with the name '%1' already exists.": "Ein Workflow mit dem Namen '%1' existiert bereits.",
            "Rename Workflow": "Workflow umbenennen",
            "New display name:": "Neuer Anzeigename:",
            "A rule with the name '%1' already exists.": "Eine Regel mit dem Namen '%1' existiert bereits.",
            "Workflow in Use": "Workflow wird verwendet",
            "Delete Workflow": "Workflow löschen",
            "Are you sure you want to delete the workflow '%1'?": "Sicher, dass Workflow '%1' gelöscht werden soll?",
        },
        "HybridAssemblerPlugin": {
            "Hybrid Assembler": "Hybrid Assembler",
            "Assembles hybrid PDFs from native and scanned versions.": "Erstellt Hybrid-PDFs aus Scans und nativen Versionen.",
            "Assemble Hybrid PDFs...": "Hybrid-PDFs erstellen...",
        },
        "MatchingDialog": {
            "Hybrid Matching-Dialog": "Hybrid-Vergleich/Merge",
            "<b>Hybrid Matching-Dialog</b><br>Finds pairs of scanned and native PDFs in a folder to merge them.": "<b>Hybrid Vergleich</b><br>Findet Scans und native PDFs in einem Ordner zum Zusammenführen.",
            "No folder selected.": "Kein Ordner gewählt.",
            "Browse Folder...": "Ordner wählen...",
            "Delete original files after successful merge": "Originaldateien nach Merge löschen",
            "Scan File": "Scan-Datei",
            "Best Native Match": "Bester nativer Treffer",
            "Actions": "Aktionen",
            "Start Analysis": "Analyse starten",
            "Start scanning folder or process results": "Ordner scannen oder Ergebnisse verarbeiten",
            "Analyzing...": "Analysiere...",
            "Merge Matched": "Treffer zusammenführen",
            "Import Merged": "Hybrid-PDFs importieren",
            "Analyzing %1 files...": "Analysiere %1 Dateien...",
            "Matching %1 Scans (Smart Two-Stage)...": "Vergleiche %1 Scans...",
            "Analysis complete. Found %1 potential scans.": "Analyse fertig. %1 Scans gefunden.",
            "Assembled": "Zusammengeführt",
            "Match": "Treffer",
            "Unsure": "Unsicher",
            "Mismatch": "Kein Treffer",
            "Verify": "Prüfen",
            "Side-by-side comparison and verification": "Vergleich und Verifizierung",
            "Merge": "Merge",
            "Imported ✓": "Importiert ✓",
            "Batch merge complete.": "Sammel-Merge abgeschlossen.",
            "Merge success: %1": "Merge erfolgreich: %1",
            "Batch Merge": "Sammel-Merge",
            "No pending matches found to merge.": "Keine ausstehenden Treffer gefunden.",
            "Select Output Folder for Hybrid PDFs": "Zielordner für Hybrid-PDFs wählen",
        },
        "OrderCollectionLinker": {
            "Order Collection Linker": "Sammlungs-Verknüpfer",
            "Order Collection Discovery Complete:": "Sammlungs-Erkennung abgeschlossen:",
            "Identified %1 collections": "%1 Sammlungen identifiziert",
            "Established %1 new organic process IDs": "%1 neue Prozess-IDs erstellt",
            "Linked %1 documents semantically": "%1 Dokumente verknüpft",
        },
    }

    # Optimization: Read tree once, update, then save once.
    tree = tool._get_tree()
    root = tree.getroot()
    
    contexts_in_ts = {ctx.findtext("name"): ctx for ctx in root.findall("context")}
    
    # 1. Apply common translations to ALL contexts that have the source
    for ctx_name, ctx_node in contexts_in_ts.items():
        for msg in ctx_node.findall("message"):
            source = msg.findtext("source")
            if source in common:
                trans_elem = msg.find("translation")
                if trans_elem is not None:
                    trans_elem.text = common[source]
                    if "type" in trans_elem.attrib:
                        del trans_elem.attrib["type"]

    # 2. Apply context-specific overrides
    for ctx_name, mapping in contexts.items():
        if ctx_name in contexts_in_ts:
            ctx_node = contexts_in_ts[ctx_name]
            for source, translation in mapping.items():
                # Find message with this source
                found = False
                for msg in ctx_node.findall("message"):
                    if msg.findtext("source") == source:
                        trans_elem = msg.find("translation")
                        if trans_elem is not None:
                            trans_elem.text = translation
                            if "type" in trans_elem.attrib:
                                del trans_elem.attrib["type"]
                        found = True
                        break

    tool._save_tree(tree)
    
    # 3. Auto-resolve shortcuts for all contexts to ensure no collisions
    # We define some "Fixed" ones for MainWindow that shouldn't change
    reserved_main = {
        "&File": "&Datei",
        "&Edit": "&Bearbeiten",
        "&View": "&Ansicht",
        "&Tools": "Werk&zeuge",
        "&Maintenance": "&Wartung",
        "&Debug": "Debu&g",
        "&Config": "&Konfiguration",
        "&Semantic Data": "&Semantische Daten",
        "&Help": "&Hilfe",
        "&Settings...": "&Einstellungen...",
        "&About": "&Über",
        "&Print": "Dr&ucken",
        "&Refresh List": "Liste &neu laden",
        "Filter Panel": "Filter-&Panel",
    }
    
    # Process all contexts found in TS
    for ctx in root.findall("context"):
        ctx_name = ctx.findtext("name")
        res = reserved_main if ctx_name == "MainWindow" else None
        tool.resolve_shortcuts_for_context(ctx_name, reserved=res)

    print("Successfully updated translations and resolved shortcuts.")

    # Final Verification
    collisions = tool.check_shortcut_collisions()
    if collisions:
        print("\nWARNING: Shortcut ampersand collisions detected within contexts:")
        for ctx, mapping in collisions.items():
            print(f"  Context: {ctx}")
            for char, sources in mapping.items():
                print(f"    Key '{char}': {', '.join(sources)}")
        print("\nPlease review these shortcuts to ensure unique keyboard navigation.")

if __name__ == "__main__":
    fill()
