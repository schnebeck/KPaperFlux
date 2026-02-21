
"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tools/fill_l10n.py
Version:        3.1.0 (Delta-Stable)
Description:    Unified orchestration script for batch-populating translations.
                Now uses a DELTA approach: preserves existing structure,
                adds missing ones, and updates mismatched ones.
------------------------------------------------------------------------------
"""

import sys
import xml.etree.ElementTree as ET
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
        "Semantic Data": "Semantische Daten",
        "&Workflows": "&Abläufe",
        "Import from Transfer": "Aus Transfer importieren",
        "Export shown List...": "Sichtbare Liste exportieren...",
        "E&xit": "B&eenden",
        "Show Extra Data": "Zusatzdaten anzeigen",
        "Filter Panel": "Filter-Panel",
        "Check Integrity (Orphans/Ghosts)": "Integrität prüfen (Waisen/Geister)",
        "Find Duplicates": "Duplikate finden",
        "Manage Tags": "Tags verwalten",
        "Purge All Data (Reset)": "Alle Daten löschen (Reset)",
        "External Plugins": "Externe Plugins",
        "Show Orphaned Vault Files": "Verwaisende Vault-Dateien anzeigen",
        "Prune Orphaned Vault Files (Console)": "Verwaiste Vault-Dateien bereinigen (Konsole)",
        "Show Broken Entity References": "Defekte Entitäts-Referenzen anzeigen",
        "Prune Broken Entity References (Console)": "Defekte Entitäts-Referenzen bereinigen (Konsole)",
        "Deduplicate Vault (Inhaltsbasiert)": "Vault deduplizieren (inhaltsbasiert)",
        "List Missing": "Fehlende auflisten",
        "List Mismatched": "Differenzen auflisten",
        "Run Extraction (Selected)": "Extraktion ausführen (Selektiert)",
        "Process empty Documents": "Leere Dokumente verarbeiten",
        "Main overview and statistics": "Hauptübersicht und Statistiken",
        "Browse and manage document list": "Dokumentenliste durchsuchen und verwalten",
        
        # Cockpit & Reporting
        "Rename...": "Umbenennen...",
        "Edit Configuration...": "Konfiguration bearbeiten...",
        "Remove from Cockpit": "Aus Cockpit entfernen",
        "Unlock Layout (Enable Dragging)": "Layout entsperren (Verschieben erlauben)",
        "Lock Layout (Prevent Dragging)": "Layout sperren (Verschieben fixieren)",
        "Add New Filter View...": "Neue Filter-Ansicht hinzufügen...",
        "Select Report:": "Zusammenfassung wählen:",
        "Add Comment": "Kommentar hinzufügen",
        "New Report": "Neue Zusammenfassung",
        "Import from PDF": "Aus PDF importieren",
        "Save Layout": "Layout speichern",
        "Load Layout": "Layout laden",
        "Export as CSV (Data)": "Als CSV exportieren (Daten)",
        "Export as PDF (Report)": "Als PDF exportieren (Bericht)",
        "Export as ZIP (Documents)": "Als ZIP exportieren (Dokumente)",
        "Digital Original (Protected Signature)": "Digitales Original (Signaturgeschützt)",
        "Digital Original (ZUGFeRD Data)": "Digitales Original (ZUGFeRD-Daten)",
        "Keep younger duplicates (%s)": "Jüngere Dubletten behalten (%s)",
        "Keep older duplicates (%s)": "Ältere Dubletten behalten (%s)",
        "Really delete %s duplicates?": "Wirklich %s Dubletten löschen?",
        "%s documents could not be deleted.": "%s Dokumente konnten nicht gelöscht werden.",
        "Select an item to view details": "Eintrag auswählen für Details",
        "New Folder": "Neuer Ordner",
        "Export to Exchange...": "Exportieren (Exchange)...",
        "Archive": "Archiv",
        "Remove from list (Ignore)": "Aus Liste entfernen (Ignorieren)",
        "Delete '%1'": "Lösche '%1'",

        # Aggregations (Cockpit/Reporting)
        "Sum": "Summe",
        "Avg": "Schnitt",
        "Count": "Anzahl",
        "Min": "Min",
        "Max": "Max",
        "Median": "Median",
        "Percent": "Prozent",
        "Inbox": "Eingang",
        "Urgent": "Dringend",
        "Review": "Prüfung",
        "Total Documents": "Belege Gesamt",
        "Total Invoiced": "Gesamtsumme",
        "Processed": "Verarbeitet",

        # Standard Workflow States & Rule Names
        "Standard Invoice Manager": "Standard Rechnungs-Workflow",
        "Incoming Invoice": "Neu Eingang",
        "Ready for Payment": "Zahlung bereit",
        "Paid & Archived": "Bezahlt & Archiv",
        "Rejected / Spam": "Abgelehnt / Spam",
        "Verify": "Prüfen",
        "Reject": "Ablehnen",
        "Mark as paid": "Als bezahlt markieren",
        "Reset": "Zurücksetzen",

        # Standard Reports
        "Monthly Invoice Count": "Rechnungseingang (Monatlich)",
        "Monthly Spending": "Ausgaben (Monatlich)",
        "Tax Summary YTD": "Steuer-Übersicht (YTD)",
        "Tax Overview": "Steuer-Übersicht",
        "Grand Totals": "Gesamtsummen",
        "Monthly Invoices": "Monatliche Rechnungen",
        
        # Context Menu (RMB)
        "Document updated (%n part(s)).": "Dokument aktualisiert (%n Teil(e)).",
        "%n document(s) selected.": "%n Dokument(e) ausgewählt.",
        "Queued %n doc(s) for background extraction.": "%n Dokument(e) für Hintergrund-Extraktion eingereiht.",
        "Import %n file(s) into KPaperFlux?": "%n Datei(en) in KPaperFlux importieren?",
        "List '%s' saved with %n item(s).": "Liste '%s' mit %n Eintrag/Einträgen gespeichert.",
        "Merge %n documents?": "%n Dokumente zusammenführen?",
        "Edit Document...": "Dokument bearbeiten...",
        "Reprocess / Re-Analyze": "Neu analysieren",
        "Show generic Document": "Generisches Dokument anzeigen",
        "Extract from Selection": "Aus Auswahl extrahieren",
        "Extract from View": "Aus Ansicht extrahieren",
        "Manage Tags...": "Tags verwalten...",
        "Stamp...": "Stempel...",
        "Apply Rule...": "Regel anwenden...",
        "No active rules found in Filter Tree.": "Keine aktiven Regeln gefunden.",
        "Save as List...": "Als Liste speichern...",
        "Export Selected...": "Auswahl exportieren...",
        "Export All Visible...": "Alle sichtbaren exportieren...",
        "Restore": "Wiederherstellen",
        "Delete Permanently": "Endgültig löschen",
        "Delete Document": "Dokument löschen",
        
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
        "UUID:": "UUID:",
        "Created At:": "Erstellt am:",
        "Pages:": "Seiten:",
        "Export Name:": "Export-Name:",
        "Archived": "Archiviert",
        "Storage Location:": "Lagerort:",
        "Locked (Immutable)": "Gesperrt (Unveränderlich)",
        
        # Logical Operators & Conditions
        "AND": "UND",
        "OR": "ODER",
        "Not": "Nicht",
        "Contains": "enthält",
        "Equals": "ist gleich",
        "Starts With": "beginnt mit",
        "Ends With": "endet mit",
        "Greater Than": "größer als",
        "Less Than": "kleiner als",
        "Is Empty": "ist leer",
        "Is Not Empty": "ist nicht leer",
        "In List": "in Liste",
        "Between": "zwischen",
        "matches": "entspricht (Regex)",
        "+ Condition": "+ Bedingung",
        "+ Group": "+ Gruppe",
        "Remove Group": "Gruppe entfernen",
        "Select Field...": "Feld wählen...",
        "Full Text": "Volltext",
        
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
            "Extracted Data": "Extrahierte Daten",
            "🔍 Audit": "🔍 Prüfung",
            "Eligible for PKV Reimbursement": "PKV-relevant",
            "Document Types:": "Dokumenttypen:",
            "Tenant Context:": "Mandantenkontext:",
            "GiroCode (EPC)": "GiroCode (EPC)",
            "Standardized QR code for SEPA transfers (EPC-QR).": "Standardiesierter QR-Code für SEPA-Überweisungen.",
            "Copy Payload": "Daten kopieren",
            "Copy the raw GiroCode data for banking apps": "Raw-GiroCode-Daten kopieren",
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
        "CockpitWidget": {
            "Inbox": "Eingang",
            "Urgent": "Dringend",
            "Total Documents": "Belege Gesamt",
            "Total Invoiced": "Gesamtsumme",
            "Review": "Prüfung",
            "Processed": "Verarbeitet"
        },
        "StatCard": {
            "Count": "Anzahl",
            "Sum": "Summe",
            "Avg": "Schnitt",
            "Min": "Min",
            "Max": "Max",
            "Median": "Median",
            "Percent": "Prozent",
            "Inbox": "Eingang",
            "Urgent": "Dringend",
            "Total Documents": "Belege Gesamt",
            "Total Invoiced": "Gesamtsumme",
            "Review": "Prüfung",
            "Processed": "Verarbeitet"
        },
        "WorkflowControlsWidget": {
            "No Workflow": "Kein Ablauf",
            "None": "Keiner",
            "Missing fields: %s": "Fehlende Felder: %s",
            "Change/Assign Rule": "Regel ändern/zuweisen",
        },
        "AdvancedFilterWidget": {
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
            "Save Rule": "Regel speichern",
            "Rule Name:": "Regelname:",
            "Delete Rule": "Regel löschen",
            "Are you sure you want to delete this rule?": "Sind Sie sicher, dass Sie diese Regel löschen möchten?",
            "Apply to ALL documents": "Auf ALLE Dokumente anwenden",
            "Apply to current List View (Filtered)": "Auf aktuelle Ansicht anwendung (gefiltert)",
            "Apply to SELECTED documents only": "Nur auf AUSGEWÄHLTE Dokumente anwenden",
            "No 'Add Tags' defined. Cannot create a filter for nothing.": "Keine Tags zum Hinzufügen definiert. Filter kann nicht erstellt werden.",
        },
        "WorkflowRuleFormEditor": {
            "Rule Name:": "Name der Regel:",
            "Description:": "Beschreibung:",
            "Regex Triggers:": "Regex Auslöser:",
            "Enter rule name...": "Regelname eingeben...",
            "What does this rule do?": "Was macht diese Regel?",
            "INVOICE, TELEKOM, ...": "RECHNUNG, TELEKOM, ...",
            "Add State": "Status hinzufügen",
            "Remove State": "Status entfernen",
            "Move State Up": "Status hoch",
            "Move State Down": "Status runter",
            "State ID": "Status ID",
            "Label": "Bezeichnung",
            "Final?": "Finale?",
            "Add Transition": "Übergang hinzufügen",
            "Remove Transition": "Übergang entfernen",
            "Move Transition Up": "Übergang hoch",
            "Move Transition Down": "Übergang runter",
            "From State": "Von Status",
            "Action": "Aktion",
            "Target State": "Ziel-Status",
            "Required Fields": "Pflichtfelder",
            "UI?": "Anzeige?",
            "Conditions": "Bedingungen",
            "States": "Zustände",
            "Transitions": "Übergänge",
        },
        "WorkflowManagerWidget": {
            "Dashboard": "Dashboard",
            "Rule Editor": "Regel-Editor",
            "Select Rule:": "Regel wählen:",
            "New Rule": "Neue Regel",
            "Create a new workflow rule": "Neue Workflow-Regel erstellen",
            "Revert": "Zurücksetzen",
            "Discard unsaved changes": "Änderungen verwerfen",
            "Save Rule": "Regel speichern",
            "Save and activate the current rule": "Regel speichern und aktivieren",
            "Manage...": "Verwalten...",
            "Manage rule files (delete, rename, import)": "Regel-Dateien verwalten",
            "Ready": "Bereit",
            "--- Select Rule ---": "--- Regel wählen ---",
            "Rule deleted.": "Regel gelöscht.",
            "Unsaved Changes": "Ungespeicherte Änderungen",
            "You have unsaved changes. Discard them?": "Es gibt ungespeicherte Änderungen. Verwerfen?",
        },
        "FilterConditionWidget": {
            "Basis": "Basis",
            "Analysis": "Analyse",
            "Stamps": "Stempel",
            "System": "System",
            "Raw Data": "Rohdaten",
            "Document Date": "Belegdatum",
            "Created At": "Erstellt am",
            "Processed At": "Zuletzt verarbeitet",
        }
    }

    # DELTA LOGIC: Work on a single tree instance
    tree = tool._get_tree()
    root = tree.getroot()
    modified = False

    def ensure_translation(ctx_node, src, trans):
        nonlocal modified
        # Find message
        msg_found = None
        for msg in ctx_node.findall("message"):
            if msg.findtext("source") == src:
                msg_found = msg
                break
        
        if msg_found is None:
            # Skip adding missing non-translated strings silently if they are not in common?
            # No, if it's in contexts list, we want it.
            msg_found = ET.SubElement(ctx_node, "message")
            s = ET.SubElement(msg_found, "source")
            s.text = src
            t = ET.SubElement(msg_found, "translation")
            t.text = trans
            modified = True
            return

        t_node = msg_found.find("translation")
        if t_node is None:
            t_node = ET.SubElement(msg_found, "translation")
        
        # Determine if we need to update
        needs_update = False
        is_unfinished = t_node.get("type") == "unfinished"
        is_vanished = t_node.get("type") == "vanished"
        
        is_numerus = msg_found.get("numerus") == "yes"
        
        if is_numerus:
            # Check if all numerusforms have the correct text
            forms = t_node.findall("numerusform")
            if not forms or any(f.text != trans for f in forms) or is_unfinished:
                needs_update = True
        else:
            if not t_node.text or is_unfinished or is_vanished or t_node.text != trans:
                needs_update = True

        if needs_update:
            if is_numerus:
                t_node.text = None
                for child in list(t_node): t_node.remove(child)
                nf1 = ET.SubElement(t_node, "numerusform")
                nf1.text = trans
                nf2 = ET.SubElement(t_node, "numerusform")
                nf2.text = trans
            else:
                t_node.text = trans
                
            if "type" in t_node.attrib:
                del t_node.attrib["type"]
            modified = True

    # 1. Apply Context-Specific mappings
    for ctx_name, trans_dict in contexts.items():
        # Find context
        ctx_node = None
        for c in root.findall("context"):
            if c.findtext("name") == ctx_name:
                ctx_node = c
                break
        if ctx_node is None:
            ctx_node = ET.SubElement(root, "context")
            n = ET.SubElement(ctx_node, "name")
            n.text = ctx_name
            modified = True
        
        for src, trans in trans_dict.items():
            ensure_translation(ctx_node, src, trans)

    # 2. Apply Common translations to ALL existing contexts that have the source
    for ctx_node in root.findall("context"):
        ctx_name = ctx_node.findtext("name")
        for msg in ctx_node.findall("message"):
            source = msg.findtext("source")
            if source in common:
                # Skip if context-specific override exists
                if ctx_name in contexts and source in contexts[ctx_name]:
                    continue
                
                ensure_translation(ctx_node, source, common[source])

    if modified:
        tool._save_tree(tree)

    # 3. Resolve shortcuts (runs its own save inside)
    for ctx_node in root.findall("context"):
        ctx_name = ctx_node.findtext("name")
        res = contexts.get(ctx_name, {})
        tool.resolve_shortcuts_for_context(ctx_name, reserved=res)

    print("Success: Localization library synchronized (Delta-Safe).")

if __name__ == "__main__":
    fill()
