
"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tools/fill_l10n.py
Version:        3.0.0
Description:    Unified orchestration script for batch-populating translations.
                Uses a single source of truth for all German UI strings.
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
    
    # Common translations applied to all contexts if not overridden
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
        "Query:": "Abfrage:",
        "Go": "Los",
        "Filter": "Filter",
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
        "Select:": "Auswahl:",
        
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
        "General": "Allgemein",
        "Vocabulary": "Vokabular",
        "Identity": "Identität",
        "Logging": "Protokollierung",
        "UUID:": "UUID:",
        "Created At:": "Erstellt am:",
        "Pages:": "Seiten:",
        "Export Name:": "Export-Name:",
        "Archived": "Archiviert",
        "Storage Location:": "Lagerort:",
        "Locked (Immutable)": "Gesperrt (Unveränderlich)",
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
            "Extracted Data": "Extrahierte Daten",
            "🔍 Audit": "🔍 Prüfung",
            "Eligible for PKV Reimbursement": "PKV-relevant",
            "Document Types:": "Dokumenttypen:",
            "Tenant Context:": "Mandantenkontext:",
            "GiroCode (EPC)": "GiroCode (EPC)",
            "Standardized QR code for SEPA transfers (EPC-QR).": "Standardiesierter QR-Code für SEPA-Überweisungen.",
            "Copy Payload": "Daten kopieren",
            "Copy the raw GiroCode data for banking apps": "Raw-GiroCode-Daten kopieren",
            "New": "Neu",
            "Ready for Pipeline": "Bereit für Pipeline",
            "Processing": "Verarbeitung",
            "Processing (Stage 1)": "Verarbeitung (Stufe 1)",
            "Processing (Stamps)": "Verarbeitung (Stempel)",
            "Processing (Semantic)": "Verarbeitung (Semantik)",
            "On Hold (Stage 1)": "Warteschlange (Stufe 1)",
            "On Hold (Stamps)": "Warteschlange (Stempel)",
            "On Hold (Semantic)": "Warteschlange (Semantik)",
            "Processed": "Verarbeitet",
            "Error": "Fehler",
            "Saved": "Gespeichert",
            "Changes saved to Database.": "Änderungen in Datenbank gespeichert.",
            "Workflow Updated": "Ablauf aktualisiert",
            "State transitioned to %1": "Status gewechselt zu %1",
            "Rule assigned: %1": "Regel zugewiesen: %1",
            "None": "Keine",
            "Audit": "Prüfung",
            "Please select a document first.": "Bitte wählen Sie zuerst ein Dokument aus.",
            "GiroCode payload copied to clipboard.": "GiroCode-Daten in die Zwischenablage kopiert.",
            "Cannot copy: Incomplete GiroCode data.": "Kopieren fehlgeschlagen: Unvollständige GiroCode-Daten.",
            "Direction:": "Richtung:",
            "Recipient:": "Empfänger:",
            "IBAN:": "IBAN:",
            "BIC:": "BIC:",
            "Amount:": "Betrag:",
            "Purpose:": "Verwendungszweck:",
            "Save Changes": "Änderungen speichern",
            "Document Date:": "Belegdatum:",
            "Sender:": "Absender:",
            "General": "Allgemein",
            "Analysis": "Analyse",
            "Payment": "Zahlung",
            "Stamps": "Stempel",
            "Semantic Data": "Semantische Daten",
            "Source Mapping": "Quell-Komponenten",
            "Debug Data": "Debug-Daten",
            "History": "Historie",
        },
        "WorkflowControlsWidget": {
            "No Workflow": "Kein Ablauf",
            "None": "Keiner",
            "Missing fields: %s": "Fehlende Felder: %s",
            "Change/Assign Rule": "Regel ändern/zuweisen",
        },
        "AdvancedFilterWidget": {
            "Search": "Suche",
            "Filter": "Filter",
            "Rules": "Regeln",
            "--- Saved Filter ---": "--- Filter laden ---",
            "--- Saved Rule ---": "--- Regeln laden ---",
            "Advanced Filter \u25BC": "Erweiterter Filter \u25BC",
            "e.g. Amazon 2024 Invoice...": "z.B. Amazon 2024 Rechnung...",
            "e.g. tax": "z.B. Steuer",
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
            "Create View-filter": "Ansicht-Filter erstellen",
            "Revert Changes": "Änderungen verwerfen",
            "Manage Filters": "Filter verwalten",
            "Export filter": "Filter exportieren",
            "Filter Created": "Filter erstellt",
            "A new view filter '%s' has been created in the 'Views' folder.": "Ein neuer Ansichts-Filter '%s' wurde im Ordner 'Ansichten' erstellt.",
            "Filter Name:": "Filtername:",
            "Search": "Suche",
            "Filter": "Filter",
            "Rules": "Regeln",
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
            "Save Rule": "Regel speichern",
            "Manage...": "Verwalten...",
            "Ready": "Bereit",
            "Error": "Fehler",
        },
        "FilterManagerDialog": {
            "Management for Filters and Rules": "Verwaltung für Filter und Regeln",
            "Search filters...": "Suche...",
            "<b>Select an item</b> to view details": "<b>Wähle ein Element</b> für Details",
            "AND": "UND",
            "OR": "ODER",
            "equals": "ist gleich",
            "contains": "enthält",
            "starts with": "beginnt mit",
            "ends with": "endet mit",
            "greater than": "größer als",
            "less than": "kleiner als",
            "Is Empty": "ist leer",
            "Is Not Empty": "ist nicht leer",
            "in list": "in Liste",
            "between": "zwischen",
            "matches": "entspricht (Regex)",
            "NOT ": "NICHT ",
        },
        "FilterConditionWidget": {
            "Equals": "ist gleich",
            "Greater Than": "größer als",
            "Less Than": "kleiner als",
            "Starts With": "beginnt mit",
            "Full Text": "Volltext",
            "Document Date": "Belegdatum",
            "Created At": "Erstellt am",
            "Processed At": "Zuletzt verarbeitet",
        }
    }

    # 1. First, set specific translations
    for ctx_name, trans_dict in contexts.items():
        for source, translation in trans_dict.items():
            tool.update_translation(ctx_name, source, translation)

    # 2. Then, set common for ALL contexts that have these source strings
    import xml.etree.ElementTree as ET
    tree = tool._get_tree()
    root = tree.getroot()
    
    modified = False
    for ctx_node in root.findall("context"):
        ctx_name = ctx_node.findtext("name")
        for msg in ctx_node.findall("message"):
            source = msg.findtext("source")
            if source in common:
                # Check if already translated (and not overriding context specific)
                if ctx_name in contexts and source in contexts[ctx_name]:
                    continue
                
                trans_elem = msg.find("translation")
                if trans_elem is None:
                    trans_elem = ET.SubElement(msg, "translation")
                
                # Only update if empty or "unfinished"
                if not trans_elem.text or trans_elem.get("type") == "unfinished":
                    trans_elem.text = common[source]
                    if "type" in trans_elem.attrib:
                        del trans_elem.attrib["type"]
                    modified = True

    if modified:
        tool._save_tree(tree)

    # 3. Resolve shortcuts
    for ctx_node in root.findall("context"):
        ctx_name = ctx_node.findtext("name")
        res = contexts.get(ctx_name, {})
        tool.resolve_shortcuts_for_context(ctx_name, reserved=res)

    print("Success: Localization library synchronized.")

if __name__ == "__main__":
    fill()
