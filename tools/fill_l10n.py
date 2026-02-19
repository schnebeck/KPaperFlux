
"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           fill_l10n.py
Version:        2.3.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Gemini 3pro
Description:    Orchestration script for batch-populating translations into
                the .ts file using L10nTool. Serves as the central mapping
                authority for German UI strings.
------------------------------------------------------------------------------
"""

import sys
from pathlib import Path
from l10n_tool import L10nTool

def fill():
    ts_path = Path(__file__).parent.parent / "resources" / "l10n" / "de" / "gui_strings.ts"
    if not ts_path.exists():
        print(f"Error: .ts file not found at {ts_path}")
        return

    tool = L10nTool(str(ts_path))
    
    # Common translations applied to all contexts
    common = {
        # Menus & Actions
        "&File": "&Datei",
        "&Edit": "&Bearbeiten",
        "&View": "&Ansicht",
        "&Tools": "Werk&zeuge",
        "&Help": "&Hilfe",
        "&Debug": "Debu&g",
        "&Config": "&Konfiguration",
        "&Settings...": "&Einstellungen...",
        "&About": "&Über",
        "&Import Document": "Dokument &importieren",
        "&Scan...": "&Scannen...",
        "&Print": "Dr&ucken",
        "&Delete Selected": "Auswahl &löschen",
        "&Refresh List": "Liste &neu laden",
        "&Maintenance": "&Wartung",
        "&Semantic Data": "&Semantische Daten",
        "&Workflows": "&Abläufe",
        
        # Standard Buttons & Labels
        "OK": "OK",
        "Cancel": "Abbrechen",
        "Close": "Schließen",
        "Save": "Speichern",
        "Save...": "Speichern...",
        "Delete": "Löschen",
        "Add": "Hinzufügen",
        "Edit": "Bearbeiten",
        "Search": "Suchen",
        "Search:": "Suche:",
        "Go": "Los",
        "Filter": "Filtern",
        "Filter:": "Filter:",
        "Rules": "Regeln",
        "Tags:": "Tags:",
        "Status:": "Status:",
        "Date:": "Datum:",
        "Type:": "Typ:",
        "Mode:": "Modus:",
        "Color:": "Farbe:",
        "Title:": "Titel:",
        "Ready": "Bereit",
        "Confirm": "Bestätigen",
        "Success": "Erfolg",
        "Warning": "Warnung",
        "Error": "Fehler",
        "Info": "Info",
        "Rename": "Umbenennen",
        "Merge": "Zusammenführen",
        "Export": "Exportieren",
        "Browse...": "Durchsuchen...",
        "Fit": "Einpassen",
        "Clear All": "Alles leeren",
        "Apply": "Anwenden",
        "Apply Changes": "Anwenden",
        "Active": "Aktiv",
        "Discard": "Verwerfen",
        "Revert": "Zurücksetzen",
        "Manage": "Verwalten",
        
        # Business Terms
        "Inbound": "Eingang",
        "Outbound": "Ausgang",
        "Internal": "Intern",
        "Private": "Privat",
        "Business": "Geschäftlich",
        "Workflows": "Abläufe",
        "Dashboard": "Dashboard",
        "Reports": "Berichte",
        "Cockpit": "Cockpit",
        "Documents": "Dokumente",
        "Settings": "Einstellungen",
    }

    # Context-specific overrides
    contexts = {
        "MainWindow": {
            "Filter Panel": "Filter-&Panel",
            "Docs: %s/%s": "Doks: %s/%s",
            "AI: %s": "KI: %s",
            "Check Integrity (Orphans/Ghosts)": "Integrität prüfen (Waisen/Geister)",
        },
        "MetadataEditorWidget": {
            "--- Extracted Data ---": "--- Extrahierte Daten ---",
            "🔍 Audit": "🔍 Prüfung",
            "Eligible for PKV Reimbursement": "PKV-relevant",
            "Document Types:": "Dokumenttypen:",
            "Tenant Context:": "Mandantenkontext:",
            "GiroCode (EPC)": "GiroCode (EPC)",
            "Standardized QR code for SEPA transfers (EPC-QR).": "Standardiesierter QR-Code für SEPA-Überweisungen.",
            "Copy Payload": "Daten kopieren",
            "Copy the raw GiroCode data for banking apps": "Raw-GiroCode-Daten kopieren",
        },
        "AdvancedFilterWidget": {
            "Search": "Suche",
            "Filter": "Filter",
            "Rules": "Regeln",
            "--- Saved Filter ---": "--- Filter läden ---",
            "--- Saved Rule ---": "--- Regeln laden ---",
            "Advanced Filter \u25BC": "Erweiterter Filter \u25BC",
            "e.g. Amazon 2024 Invoice...": "z.B. Amazon 2024 Rechnung...",
            "e.g. tax": "z.B. Steuer",
            "Select:": "Auswahl:",
            "Discard": "Verwerfen",
            "Save": "Speichern",
            "Save...": "Speichern...",
            "Manage": "Verwalten",
            "Export": "Exportieren",
            "Revert": "Verwerfen",
            "Clear All": "Alles leeren",
            "Apply Changes": "Änderungen übernehmen",
            "Search in current view only": "Nur in aktueller Ansicht suchen",
            "Filter Active": "Filter aktiv",
            "If checked, combines the search with the active filters from 'Filter View'.": "Kombiniert die Suche mit den aktiven Filtern der Ansicht.",
            "Apply to all": "Auf alle anwenden",
            "Apply to View": "Auf Ansicht anwenden",
            "Add Tags:": "Tags hinzufügen:",
            "Remove Tags:": "Tags entfernen:",
            "Assign Workflow:": "Ablauf zuweisen:",
            "--- No Change ---": "--- Keine Änderung ---",
            "Run on Import": "Bei Import ausführen",
            "Active": "Aktiv",
        },
        "BatchTagDialog": {
            "<b>Checked Tags:</b> Will be present on ALL selected documents (Merged).<br><b>Unchecked Tags:</b> Will be REMOVED from ALL selected documents (if they were common).<br><i>Individual unique tags on specific documents are preserved unless forced removed.</i>": "<b>Aktivierte Tags:</b> Werden auf ALLEN gewählten Dokumenten gesetzt.<br><b>Deaktivierte Tags:</b> Werden von ALLEN gewählten Dokumenten ENTFERNT.<br><i>Individuelle Tags bleiben erhalten, sofern nicht 'Gemischte entfernen' aktiv ist.</i>",
        },
        "DocumentListWidget": {
            "Digital Original (Signed)": "Digitales Original (Signiert)",
            "Digital Original (ZUGFeRD/Factur-X)": "Digitales Original (ZUGFeRD)",
            "Digital Original (Signed & ZUGFeRD)": "Digitales Original (Signiert & ZUGFeRD)",
            "Hybrid Container (KPaperFlux Protected)": "Hybrid-Container (KPaperFlux)",
            "Trash Bin": "Mülleimer",
        },
        "MatchingDialog": {
            "<b>Hybrid Matching-Dialog</b><br>Finds pairs of scanned and native PDFs in a folder to merge them.": "<b>Hybrid Vergleich</b><br>Findet Scans und native PDFs in einem Ordner zum Zusammenführen.",
            "Analyzing %1 files...": "Analysiere %1 Dateien...",
            "Matching %1 Scans (Smart Two-Stage)...": "Vergleiche %1 Scans...",
            "Start Analysis": "Analyse starten",
            "Analyzing...": "Analyse läuft...",
            "Merge Matched": "Matche zusammenführen",
            "Import Merged": "Hybride importieren",
            "Browse Folder...": "Ordner wählen...",
            "No folder selected.": "Kein Ordner gewählt.",
            "Delete original files after successful merge": "Originale nach Zusammenführung löschen",
            "Scan File": "Scan-Datei",
            "Best Native Match": "Bester Treffer (Digital)",
            "Status": "Status",
            "Actions": "Aktionen",
            "Assembled": "Zusammengesetzt",
            "Imported": "Importiert",
            "Imported ✓": "Importiert ✓",
            "Verify": "Prüfen",
            "Side-by-side comparison and verification": "Gegenüberstellung und Verifizierung",
        },
        "ComparisonDialog": {
            "Document Comparison": "Dokumenten-Vergleich",
            "Mismatch": "Fehlmatch",
            "Match OK": "Match OK",
        },
        "AuditWindow": {
            "KPaperFlux - Audit & Verification": "KPaperFlux - Prüfung & Verifizierung",
            "No document selected.": "Kein Dokument ausgewählt.",
        },
        "ReportingWidget": {
            "Select Report:": "Bericht wählen:",
            "Add Comment": "Kommentar hinzufügen",
            "New Report": "Neuer Bericht",
            "Import from PDF": "Aus PDF importieren",
            "Clear": "Leeren",
            "Save Layout": "Layout speichern",
            "Load Layout": "Layout laden",
            "Export": "Exportieren",
            "Export as CSV (Data)": "Als CSV exportieren (Daten)",
            "Export as PDF (Report)": "Als PDF exportieren (Bericht)",
            "Export as ZIP (Documents)": "Als ZIP exportieren (Dokumente)",
            "Select a Report": "Bericht auswählen",
            "Detailed Data": "Detaildaten",
            "Trend Analysis": "Trendanalyse",
            "Vendor Distribution": "Verteilung nach Absender",
            "Bar Chart": "Balkendiagramm",
            "Pie Chart": "Tortendiagramm",
            "Annotation / Comment": "Anmerkung / Kommentar",
            "Please select a report to display data.": "Bitte wählen Sie einen Bericht aus.",
        },
        "ReportEditorWidget": {
            "Report Name:": "Berichtsname:",
            "Description:": "Beschreibung:",
            "Group By:": "Gruppieren nach:",
            "Aggregations:": "Berechnungen (Aggregat):",
            "Data Source (Filter):": "Datenquelle (Filter):",
            "Show as:": "Darstellung:",
            "Add Aggregation": "Berechnung hinzufügen",
            "Remove Selected": "Auswahl entfernen",
            "Save Report Definition": "Berichtsdefinition speichern",
            "Table": "Tabelle",
            "Bar Chart": "Balkendiagramm",
            "Pie Chart": "Tortendiagramm",
            "Trend": "Trend",
            "CSV Export": "CSV Export",
            "Import from Saved Filter": "Aus gespeichertem Filter laden",
            "Field": "Feld",
            "Operation": "Operation",
            "Select 'amount:X' for histogram view (grouping by price ranges).": "Nutzen Sie 'amount:X' für Histogramme (Preisbereiche).",
        },
    }

    import xml.etree.ElementTree as ET
    tree = tool._get_tree()
    root = tree.getroot()
    
    for ctx_node in root.findall("context"):
        ctx_name = ctx_node.findtext("name")
        for msg in ctx_node.findall("message"):
            source = msg.findtext("source")
            comment = msg.findtext("comment")
            
            translation = None
            if ctx_name in contexts:
                ctx_map = contexts[ctx_name]
                if (source, comment) in ctx_map:
                    translation = ctx_map[(source, comment)]
                elif source in ctx_map:
                    translation = ctx_map[source]
            
            if not translation and source in common:
                translation = common[source]
            
            if not translation:
                clean_source = source.replace("&", "")
                if clean_source in common:
                    translation = common[clean_source]
            
            if translation:
                trans_elem = msg.find("translation")
                if trans_elem is None:
                    trans_elem = ET.SubElement(msg, "translation")
                trans_elem.text = translation
                if "type" in trans_elem.attrib:
                    del trans_elem.attrib["type"]

    tool._save_tree(tree)
    
    de_library = {
        "MainWindow": {
            "&File": "&Datei",
            "&Edit": "&Bearbeiten",
            "&View": "&Ansicht",
            "&Tools": "Werk&zeuge",
            "&Maintenance": "&Wartung",
            "&Debug": "Debu&g",
            "&Config": "&Konfiguration",
            "&Semantic Data": "&Semantische Daten",
            "&Help": "&Hilfe",
            "&Workflows": "&Abläufe",
        },
        "WorkflowDashboardWidget": {
            "Active Rule Load:": "Aktive Regelauslastung:",
            "Workflow Rule": "Ablaufregel",
            "Active Documents": "Aktive Dokumente",
            "Completion Rate": "Abschlussquote",
            "Total in Pipeline": "Gesamt im Ablauf",
            "Urgent Actions": "Dringende Aufgaben",
            "New Tasks": "Neue Aufgaben",
        },
        "WorkflowManagerWidget": {
            "Dashboard": "Dashboard",
            "Rule Editor": "Regel-Editor",
            "Select Rule:": "Regel wählen:",
            "New Rule": "Neue Regel",
            "Create a new workflow rule": "Neue Ablaufregel erstellen",
            "Revert": "Verwerfen",
            "Discard unsaved changes": "Änderungen verwerfen",
            "Save Rule": "Regel speichern",
            "Save and activate the current rule": "Regel speichern und aktivieren",
            "Manage...": "Verwalten...",
            "Manage rule files (delete, rename, import)": "Regeldatei verwalten",
            "Ready": "Bereit",
            "Error": "Fehler",
            "Failed to save rule: %1": "Fehler beim Speichern der Regel: %1",
        },
        "WorkflowRuleFormEditor": {
            "Rule Name:": "Name der Regel:",
            "Description:": "Beschreibung:",
            "Regex Triggers:": "Regex Trigger:",
            "INVOICE, TELEKOM, ...": "RECHNUNG, TELEKOM, ...",
            "Add State": "Status hinzufügen",
            "Remove State": "Status entfernen",
            "Move State Up": "Status nach oben",
            "Move State Down": "Status nach unten",
            "State ID": "Status-ID",
            "Label": "Bezeichnung",
            "Final?": "Final?",
            "Add Transition": "Abfolge hinzu",
            "Remove Transition": "Abfolge weg",
            "Move Transition Up": "Abfolge nach oben",
            "Move Transition Down": "Abfolge nach unten",
            "From State": "Von Status",
            "Action": "Aktion",
            "Target State": "Ziel-Status",
            "Required Fields": "Pflichtfelder",
            "UI?": "UI?",
            "Conditions": "Bedingungen",
            "States": "Stati",
            "Transitions": "Abfolgen",
            "New State": "Neuer Status",
        },
        "WorkflowRuleManagerDialog": {
            "Manage Rules": "Regeln verwalten",
            "Delete selected rule files (DEL)": "Gewählte Regeln löschen (ENTF)",
            "Close": "Schließen",
            "Delete Rule": "Regel löschen",
            "Are you sure you want to delete the rule '%1'?": "Soll die Regel '%1' gelöscht werden?",
            "Delete Rules": "Regeln löschen",
            "Are you sure you want to delete %n selected rule(s)?": "Sollen %n gewählte Regeln gelöscht werden?",
            "Rules in Use": "Regeln in Benutzung",
            "The following rules cannot be deleted because they are still in use:\n\n%1": "Folgende Regeln sind noch in Benutzung und können nicht gelöscht werden:\n\n%1",
        },
        "AdvancedFilterWidget": {
            "Search": "Suche",
            "Filter": "Filter",
            "Rules": "Regeln",
            "--- Saved Filter ---": "--- Filter läden ---",
            "--- Saved Rule ---": "--- Regeln laden ---",
            "Advanced Filter \u25BC": "Erweiterter Filter \u25BC",
            "e.g. Amazon 2024 Invoice...": "z.B. Amazon 2024 Rechnung...",
            "e.g. tax": "z.B. Steuer",
            "Select:": "Auswahl:",
            "Discard": "Verwerfen",
            "Save": "Speichern",
            "Save...": "Speichern...",
            "Manage": "Verwalten",
            "Export": "Exportieren",
            "Revert": "Verwerfen",
            "Clear All": "Alles leeren",
            "Apply Changes": "Änderungen übernehmen",
            "Search in current view only": "Nur in aktueller Ansicht suchen",
            "Filter Active": "Filter aktiv",
            "If checked, combines the search with the active filters from 'Filter View'.": "Kombiniert die Suche mit den aktiven Filtern der Ansicht.",
            "Apply to all": "Auf alle anwenden",
            "Apply to View": "Auf Ansicht anwenden",
            "Add Tags:": "Tags hinzufügen:",
            "Remove Tags:": "Tags entfernen:",
            "Assign Workflow:": "Ablauf zuweisen:",
            "--- No Change ---": "--- Keine Änderung ---",
            "Run on Import": "Bei Import ausführen",
            "Active": "Aktiv",
            "Trash": "Papierkorb",
            "Archive": "Archiv",
            "Description:": "Beschreibung:",
        },
        "FilterManagerDialog": {
            "Management for Filters and Rules": "Verwaltung für Filter und Regeln",
            "Search filters...": "Suche...",
            "<b>Select an item</b> to view details": "<b>Wähle ein Element</b> für Details",
            "Folder": "Ordner",
            "Contains %n item(s).": "Enthält %n Element(e).",
            "Deleted documents live here.": "Hier liegen gelöschte Dokumente.",
            "Select this filter to restore or permanently delete files.": "Wähle diesen Filter, um Dateien wiederherzustellen oder endgültig zu löschen.",
            "Your long-term document storage.": "Dein Langzeit-Archiv.",
            "This filter shows all documents marked as Archive.": "Dieser Filter zeigt alle als Archiv markierten Dokumente.",
            "Static List": "Statische Liste",
            "Contains <b>%n</b> documents.": "Enthält <b>%n</b> Dokument(e).",
            "and %n more.": "und %n weitere.",
            "AI Direction": "KI-Richtung",
            "AI Context": "KI-Kontext",
            "AI Confidence": "KI-Vertrauen",
            "AI Reasoning": "KI-Begründung",
            "Type Tags": "Typ-Tags",
            "Visual Audit": "Visuelle Prüfung",
            "Filename": "Dateiname",
            "Created At": "Erstellt am",
            "Last Processed": "Zuletzt verarbeitet",
            "Pages": "Seiten",
            "Text Content": "Textinhalt",
            "Filter Rule": "Filter-Regel",
            "Tagging Actions": "Tagging-Aktionen",
            "Add": "Hinzufügen",
            "Remove": "Entfernen",
            "Active": "Aktiv",
            "Inactive": "Inaktiv",
            "Run on Import": "Bei Import ausführen",
            "Settings": "Einstellungen",
            "Filtering Logic": "Filter-Logik",
            "Archive": "Archiv",
            "Trash": "Papierkorb",
            "AND": "UND",
            "OR": "ODER",
            "equals": "ist gleich",
            "contains": "enthält",
            "starts with": "beginnt mit",
            "ends with": "endet mit",
            "greater than": "größer als",
            "less than": "kleiner als",
            "in list": "in Liste",
            "between": "zwischen",
            "matches": "entspricht (Regex)",
            "NOT ": "NICHT ",
            "New Folder": "Neuer Ordner",
            "Folder Name:": "Ordnername:",
            "Delete": "Löschen",
            "Close": "Schließen",
            "Delete '%1'?": "'%1' löschen?",
            "Delete %n selected item(s)?": "%n gewählte Elemente löschen?",
            "Export to Exchange...": "Als Exchange exportieren...",
            "Move Failed": "Verschieben fehlgeschlagen",
        }
    }
    
    # Context-specific overrides if needed (optional)
    library_overrides = {
        "MatchingDialog": {
            "<b>Hybrid Matching-Dialog</b><br>Finds pairs of scanned and native PDFs in a folder to merge them.": "<b>Hybrid Vergleich</b><br>Findet Scans und native PDFs in einem Ordner zum Zusammenführen.",
             # ... more can go here
        }
    }

    # 1. First, set translations for all contexts
    for ctx_name, trans_dict in de_library.items():
        for source, translation in trans_dict.items():
            tool.update_translation(ctx_name, source, translation)

    # 2. Then resolve shortcuts for all contexts found in TS
    tree = tool._get_tree()
    root = tree.getroot()
    for ctx_node in root.findall("context"):
        ctx_name = ctx_node.findtext("name")
        res = de_library.get(ctx_name, {})
        tool.resolve_shortcuts_for_context(ctx_name, reserved=res)

    print("Success: Localization library synchronized.")

if __name__ == "__main__":
    fill()
