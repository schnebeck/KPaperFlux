
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
        "Search string too short (min 3 chars)": "Suchbegriff zu kurz (min. 3 Zeichen)",
        "Searching for duplicates...": "Suche nach Duplikaten...",
        "Searching...": "Suche...",
        "%1 error(s) occurred during reprocessing. Check logs.": "%1 Fehler bei der Verarbeitung aufgetreten. Details im Log.",
        "Processing Error": "Fehler bei der Verarbeitung",
        "Reprocessing...": "Wird neu verarbeitet...",
        "Running OCR...": "OCR wird ausgeführt...",
        "%1 documents found (%2 occurrences)": "%1 Dokumente gefunden (%2 Treffer)",
        "%1 documents found": "%1 Dokumente gefunden",
        "No documents found": "Keine Dokumente gefunden",
        "Selection Gross (total): %s EUR": "Auswahl Brutto (gesamt): %s EUR",
        "Force OCR / Searchable PDF": "OCR erzwingen / Durchsuchbares PDF",
        "Copied!": "Kopiert!",
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
        "&Semantic Data": "Semantische &Daten",
        "Semantic Data": "Semantische Daten",
        "&Workflows": "A&bläufe",
        "Import from Transfer": "Aus Transfer importieren",
        "Export shown List...": "Sichtbare Liste exportieren...",
        "E&xit": "Be&enden",
        "Show Extra Data": "Zusatzdaten anzeigen",
        "Filter Panel": "Filter-Panel",
        "Check Integrity (Orphans/Ghosts)": "Daten prüfen",
        "Find Duplicates": "Duplikate finden",
        "Manage Tags": "Tags verwalten",
        "Purge All Data (Reset)": "alle Daten zurücksetzen",
        "External Plugins": "Externe Plugins",
        "Show Orphaned Vault Files": "Verwaiste Dateien anzeigen",
        "Prune Orphaned Vault Files (Console)": "verwaiste Dateien löschen",
        "Show Broken Entity References": "Defekte Entitäts-Referenzen anzeigen",
        "Prune Broken Entity References (Console)": "defekte Referenzen löschen",
        "Deduplicate Vault (Inhaltsbasiert)": "Duplikate löschen",
        "List Missing": "Fehlende auflisten",
        "List Mismatched": "Differenzen auflisten",
        "Run Extraction (Selected)": "KI-Analyse starten",
        "Process empty Documents": "Leere Dokumente verarbeiten",
        "Main overview and statistics": "Hauptübersicht und Statistiken",
        "Browse and manage document list": "Dokumentenliste durchsuchen und verwalten",
        
        # Cockpit & Reporting
        "Rename...": "Umbenennen...",
        "Edit Configuration...": "Konfiguration bearbeiten...",
        "Remove from Cockpit": "Aus Cockpit entfernen",
        "Unlock Layout (Enable Dragging)": "Bearbeitungsmodus ein",
        "Lock Layout (Prevent Dragging)": "Bearbeitungsmodus aus",
        "Add New Filter View...": "Neue Filter-Ansicht hinzufügen...",
        "Select Report:": "Zusammenfassung wählen:",
        "Add Comment": "Kommentar hinzufügen",
        "New Report": "Neue Zusammenfassung",
        "Import from PDF": "Aus PDF importieren",
        "Save Layout": "Layout speichern",
        "Load Layout": "Layout laden",
        "Export as CSV (Data)": "CSV-Datenexport",
        "Export as PDF (Report)": "PDF-Berichtsexport",
        "Export as ZIP (Documents)": "ZIP-Archiv",
        "Digital Original (Protected Signature)": "Digitale Signatur",
        "Digital Original (ZUGFeRD Data)": "ZUGFeRD-Daten",
        "Keep younger duplicates (%s)": "Jüngere Dubletten behalten (%s)",

        # Subscription & Recurring
        "Subscription / Recurring": "Abonnement / Wiederkehrend",
        "Recurring Payment / Subscription": "Wiederkehrende Zahlung / Abonnement",
        "Frequency:": "Intervall:",
        "Service Start:": "Leistungsbeginn:",
        "Service End:": "Leistungsende:",
        "Next Billing:": "Nächste Abrechnung:",
        "Once": "Einmalig",
        "Daily": "Täglich",
        "Weekly": "Wöchentlich",
        "Monthly": "Monatlich",
        "Quarterly": "Quartalsweise",
        "Yearly": "Jährlich",
        "Subscriptions & Contracts": "Abos & Verträge",
        "Contract Details": "Vertragsdetails",
        "Contract ID:": "Vertragsnummer:",
        "Effective Date:": "Vertragsbeginn:",
        "Valid Until:": "Gültig bis:",
        "Renewal Clause:": "Verlängerung:",
        "Notice Period": "Kündigungsfrist",
        "Value:": "Wert:",
        "Unit:": "Einheit:",
        "Anchor:": "Anker:",
        "Original Text:": "Originaltext:",
        "Service Period Start:": "Leistungsbeginn:",
        "Service Period End:": "Leistungsende:",
        "None": "Keine",
        "Days": "Tage",
        "Weeks": "Wochen",
        "Months": "Monate",
        "Years": "Jahre",
        
        # General Labels
        "Keep older duplicates (%s)": "Ältere Dubletten behalten (%s)",
        "Really delete %n duplicates?": ("%n Dublette wirklich löschen?", "%n Dubletten wirklich löschen?"),
        "%n documents could not be deleted.": ("%n Dokument konnte nicht gelöscht werden.", "%n Dokumente konnten nicht gelöscht werden."),
        "Select an item to view details": "Eintrag auswählen für Details",
        "New Folder": "Neuer Ordner",
        "Export to Exchange...": "Filter exportieren",
        "Archive": "Archiv",
        "Remove from list (Ignore)": "Auswahl ausblenden",
        "Delete '%1'": "Lösche '%1'",

        # Aggregations (Cockpit/Reporting)
        "Sum": "Summe",
        "Avg": "Schnitt",
        "Count": "Anzahl",
        "Min": "Min",
        "Max": "Max",
        "Median": "Median",
        "Percent": "Prozent",
        "Inbox": "Unbearbeitete Dokumente",
        "Urgent": "Dringend",
        "Review": "Prüfung",
        "Total Documents": "Belege gesamt",
        "Total Invoiced": "Gesamtsumme",
        "Processed": "Verarbeitet",

        # Standard Workflow States & Rule Names
        "Standard Invoice Manager": "Standard Rechnungs-Workflow",
        "Incoming Invoice": "Rechnungseingang",
        "Ready for Payment": "Zahlung bereit",
        "Paid & Archived": "Bezahlt && Archiv",
        "Rejected / Spam": "Abgelehnt / Spam",
        "Verify": "Prüfen",
        "Reject": "Ablehnen",
        "Mark as paid": "Als bezahlt markieren",
        "Reset": "Zurücksetzen",

        # Standard Reports
        "Monthly Invoice Count": "Monatlicher Belegeingang",
        "Monthly Spending": "Monatliche Ausgaben",
        "Tax Summary YTD": "Steuerübersicht (YTD)",
        "Tax Overview": "Steuerübersicht",
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
        "Locked (Immutable)": "Dokument ist schreibgeschützt",
        
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
        "matches": "regulärer Ausdruck",
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
            "Check Integrity (Orphans/Ghosts)": "Daten prüfen",
            "All documents have semantic data.": "Alle Dokumente haben semantische Daten.",
            "No data mismatches found.": "Keine Datenkonflikte gefunden.",
            "Showing %s docs with missing semantic data.": "%s Dokumente ohne semantische Daten.",
            "Showing %s docs with data mismatches.": "%s Dokumente mit Datenkonflikten.",
            "Are you sure you want to delete %s items?": "%s Element(e) wirklich löschen?",
            "Deleted %s items.": "%s Element(e) gelöscht.",
            "Reprocessing %s of %s...": "Verarbeite %s von %s...",
            "%n error(s) occurred during reprocessing. Check logs.": ("%n Fehler bei der Verarbeitung aufgetreten. Details im Log.", "%n Fehler bei der Verarbeitung aufgetreten. Details im Log."),
            "Importing %s/%s: %s": "Importiere %s/%s: %s",
            "Found %s files in transfer folder. Do you want to import them now?": "%s Dateien im Transfer-Ordner gefunden. Jetzt importieren?",
            "Queued %s docs for extraction.": "%s Dokumente für Extraktion vorgemerkt.",
            "Start semantic extraction for %s documents without details?": "Semantische Extraktion für %s Dokumente ohne Details starten?",
            "Merge error: %s": "Zusammenführungsfehler: %s",
            "<h3>KPaperFlux v1.0</h3><p>A modern document management tool.</p><hr><p><b>Qt Version:</b> %1</p><p><b>Python:</b> %2</p><p><b>System:</b> %3</p><p><b>Desktop Environment:</b> %4</p>": "<h3>KPaperFlux v1.0</h3><p>Modernes Dokumentenmanagementsystem.</p><hr><p><b>Qt-Version:</b> %1</p><p><b>Python:</b> %2</p><p><b>System:</b> %3</p><p><b>Desktopumgebung:</b> %4</p>",
            "Comparing documents (%s/%s)...": "Dokumente werden verglichen (%s/%s)...",
            "Imported %s documents.\nBackground processing started.": "%s Dokumente importiert.\nHintergrundverarbeitung gestartet.",
            "Could not locate physical file for UUID: %s": "Physische Datei für UUID nicht gefunden: %s",
            "Stamp applied to %n document(s).": ("Stempel auf %n Dokument angewendet.", "Stempel auf %n Dokumente angewendet."),
            "Stamping operation failed: %s": "Stempel-Operation fehlgeschlagen: %s",
            "Updated tags for %n documents.": ("Tags für %n Dokument aktualisiert.", "Tags für %n Dokumente aktualisiert."),
            "Restored %n document(s).": ("%n Dokument wiederhergestellt.", "%n Dokumente wiederhergestellt."),
            "Permanently deleted %n document(s).": ("%n Dokument endgültig gelöscht.", "%n Dokumente endgültig gelöscht."),
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
            "Auto-transition triggered": "Automatischer Übergang ausgelöst",
            "Action triggered via UI": "Aktion per Oberfläche ausgelöst",
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
            "Inbox": "Unbearbeitete Dokumente",
            "Urgent": "Dringend",
            "Total Documents": "Belege gesamt",
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
            "Inbox": "Unbearbeitete Dokumente",
            "Urgent": "Dringend",
            "Total Documents": "Belege gesamt",
            "Total Invoiced": "Gesamtsumme",
            "Review": "Prüfung",
            "Processed": "Verarbeitet"
        },
        "CockpitEntryDialog": {
            "Inbox (NEW)": "Unbearbeitete Dokumente",
            "Total Documents": "Belege gesamt",
            "Processed Documents": "Verarbeitete Belege",
            "Urgent Workflows": "Dringende Abläufe",
            "Review Workflows": "Abläufe in Prüfung",
            "Count documents": "Belege zählen",
            "Sum amounts (€)": "Beträge summieren",
        },
        "WorkflowControlsWidget": {
            "No Workflow": "Kein Ablauf",
            "None": "Keiner",
            "Missing fields: %s": "Fehlende Felder: %s",
            "Change/Assign Rule": "Regel ändern/zuweisen",
            "Rule '%s' missing": "Regel '%s' nicht gefunden",
            "START — Entry point": "Einstiegspunkt",
            "NORMAL — Intermediate": "Zwischenzustand",
            "END OK — Positive terminal": "Positiver Abschluss",
            "END NOK — Negative terminal": "Negativer Abschluss",
            "END NEUTRAL — Neutral terminal": "Neutraler Abschluss",
            "Type:": "Typ:",
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
            "Search": "Suche",            "Show All": "Alle Dokumente anzeigen",

            "Filter": "Filter",
            "Rules": "Sortieren",
            "Save Rule": "Regel speichern",
            "Rule Name:": "Regelname:",
            "Delete Rule": "Regel löschen",
            "Are you sure you want to delete this rule?": "Sind Sie sicher, dass Sie diese Regel löschen möchten?",
            "Apply to ALL documents": "Auf ALLE Dokumente anwenden",
            "Apply to current List View (Filtered)": "Auf aktuelle Ansicht anwendung (gefiltert)",
            "Apply to SELECTED documents only": "Nur auf AUSGEWÄHLTE Dokumente anwenden",
            "No 'Add Tags' defined. Cannot create a filter for nothing.": "Keine Tags zum Hinzufügen definiert. Filter kann nicht erstellt werden.",            "--- Saved Rule ---": "--- Gespeicherte Regeln ---",

        },
        "AddTransitionDialog": {
            "Add Transition": "Übergang hinzufügen",
            "From State:": "Von Status:",
            "Action:": "Aktion:",
            "e.g. verify, approve, reject": "z.B. prüfen, genehmigen, ablehnen",
            "To State:": "Nach Status:",
            "Auto-transition (no user interaction)": "Automatischer Übergang (ohne Nutzeraktion)",
            "iban, total_gross, \u2026  (comma-separated)": "iban, brutto_gesamt, \u2026 (kommagetrennt)",
            "Required Fields:": "Pflichtfelder:",
        },
        "WorkflowGraphWidget": {
            "Fit view": "Ansicht anpassen",
            "State": "Status",
            "Transition": "Übergang",
            "Delete": "Löschen",
            "Add new state": "Neuen Status hinzufügen",
            "Add transition between states": "Übergang zwischen Status hinzufügen",
            "Delete selected item": "Auswahl löschen",
            "Select a state or transition to edit its properties.": "Status oder Übergang auswählen, um Eigenschaften zu bearbeiten.",
            "Add State": "Status hinzufügen",
            "State ID (uppercase, e.g. PROCESSING):": "Status-ID (Großbuchstaben, z.B. IN_BEARBEITUNG):",
            "Display label for '%s':": "Bezeichnung für '%s':",
            "ID:": "ID:",
            "Label:": "Bezeichnung:",
            "Final state:": "Finaler Status:",
            "Type:": "Typ:",
            "START — Entry point": "Einstiegspunkt",
            "NORMAL — Intermediate": "Zwischenzustand",
            "END OK — Positive terminal": "Positiver Abschluss",
            "END NOK — Negative terminal": "Negativer Abschluss",
            "END NEUTRAL — Neutral terminal": "Neutraler Abschluss",
            "Apply": "Anwenden",
            "Action:": "Aktion:",
            "Auto:": "Automatisch:",
            "Required Fields:": "Pflichtfelder:",
            "Missing fields: %s": "Fehlende Felder: %s",
            "Unmet conditions: %s": "Nicht erfüllte Bedingungen: %s",
        },
        "WorkflowRuleFormEditor": {
            "Rule Name:": "Name des Ablaufs:",
            "Description:": "Beschreibung:",
            "Tag Triggers:": "Tag-Auslöser:",
            "Comma-separated type_tags that activate this rule (e.g. INVOICE, ORDER_CONFIRMATION). Multiple rules may share the same tag.": "Kommagetrennte Typ-Tags, die diese Regel auslösen (z.B. RECHNUNG, AUFTRAGSBESTÄTIGUNG). Mehrere Regeln dürfen denselben Tag verwenden.",
            "Enter rule name...": "Ablaufname eingeben...",
            "What does this rule do?": "Was macht dieser Ablauf?",
            "INVOICE, ORDER_CONFIRMATION, ...": "RECHNUNG, AUFTRAGSBESTÄTIGUNG, ...",
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
            "Initial state:": "Startzustand:",
            "Mark as the designated start state of this workflow (only one per rule).": "Als festgelegten Startzustand dieses Ablaufs markieren (nur einer pro Regel möglich).",
            "Mark as a terminal state (workflow complete).": "Als Endzustand markieren (Ablauf abgeschlossen).",
            "Type:": "Typ:",
            "START — Entry point": "Einstiegspunkt",
            "NORMAL — Intermediate": "Zwischenzustand",
            "END OK — Positive terminal": "Positiver Abschluss",
            "END NOK — Negative terminal": "Negativer Abschluss",
            "END NEUTRAL — Neutral terminal": "Neutraler Abschluss",
            "Conditions:": "Bedingungen:",
            "Field": "Feld",
            "Op": "Op.",
            "Value": "Wert",
            "+ Condition": "+ Bedingung",
            "− Remove": "− Entfernen",
            "Required Fields:": "Pflichtfelder:",
            "Finance Data": "Rechnungsdaten",
            "Time-based": "Zeitbasiert",
            "Gross Amount": "Bruttobetrag",
            "IBAN": "IBAN",
            "Document Date": "Dokumentdatum",
            "Document Number": "Dokumentnummer",
            "Sender Name": "Absender",
            "Document Age (days)": "Dokumentalter (Tage)",
            "Days in Current State": "Tage im aktuellen Zustand",
            "Days Until Due": "Tage bis Fälligkeit",
        },
        "WorkflowManagerWidget": {
            "Dashboard": "Dashboard",
            "Rule Editor": "Ablaufeditor",
            "Select Rule:": "Ablauf wählen:",
            "New Rule": "Neuer Ablauf",
            "Create a new workflow rule": "Neuen Ablauf erstellen",
            "Revert": "Zurücksetzen",
            "Discard unsaved changes": "Änderungen verwerfen",
            "Save Rule": "Ablauf speichern",
            "Save and activate the current rule": "Ablauf speichern und aktivieren",
            "Manage...": "Verwalten...",
            "Manage rule files (delete, rename, import)": "Ablauf-Dateien verwalten",
            "Ready": "Bereit",
            "--- Select Rule ---": "--- Ablauf wählen ---",
            "Rule deleted.": "Ablauf gelöscht.",
            "Unsaved Changes": "Ungespeicherte Änderungen",
            "You have unsaved changes. Discard them?": "Es gibt ungespeicherte Änderungen. Verwerfen?",
            "Rules in Use": "Abläufe in Verwendung",
            "Show documents": "Dokumente anzeigen",
            "Navigate to all documents currently tracked by this workflow": "Alle Dokumente anzeigen, die diesem Ablauf zugeordnet sind",
            "Documents in workflow '%1'": "Dokumente im Ablauf '%1'",
            "Rule Saved & Reset": "Ablauf gespeichert & zurückgesetzt",
            "Rule '%s' saved.\n\n%n document(s) were reset to the initial state.": (
                "Regel '%s' gespeichert.\n\n%n Dokument wurde auf den Anfangsstatus zurückgesetzt.",
                "Regel '%s' gespeichert.\n\n%n Dokumente wurden auf den Anfangsstatus zurückgesetzt.",
            ),
            "Legacy Data Detected": "Veraltete Datenstruktur erkannt",
        },
        "FilterWidget": {
            "Rules...": "Sortieren...",
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
        },
        "DualPdfViewerWidget": {
            "Show visual differences": "Visuelle Unterschiede anzeigen",
            "Link scroll and zoom": "Scrollen und Zoom koppeln",
            "Split Document": "Dokument teilen",
        },
        "DocumentListWidget": {
            "Search": "Suche",
            "Show All": "Alle Dokumente anzeigen",
            "Hide '%1'": "'%1' ausblenden",
            "%n document(s) are locked and cannot be deleted.": ("%n Dokument ist gesperrt und kann nicht gelöscht werden.", "%n Dokumente sind gesperrt und können nicht gelöscht werden."),
            "Are you sure you want to permanently delete %n document(s)?\nThis cannot be undone.": ("%n Dokument endgültig löschen?\nDieser Vorgang kann nicht rückgängig gemacht werden.", "%n Dokumente endgültig löschen?\nDieser Vorgang kann nicht rückgängig gemacht werden."),
        },
        "ColumnManagerDialog": {
            "%s (Fixed)": "%s (Fest)",
        },
        "ExportDialog": {
            "Exporting %n documents.": ("%n Dokument wird exportiert.", "%n Dokumente werden exportiert."),
            "Export failed:\n%s": "Export fehlgeschlagen:\n%s",
            "File '%s' already exists in transfer folder. Overwrite?": "Datei '%s' existiert bereits im Transfer-Ordner. Überschreiben?",
        },
        "FilterManagerDialog": {
            "Exported to %s": "Exportiert nach %s",
        },
        "HybridAssemblerPlugin": {
            "Page count mismatch: Native PDF has %1 pages, but Scan PDF has %2 pages. Please ensure the scan is complete.": "Seitenanzahl stimmt nicht überein: Natives PDF hat %1 Seiten, Scan-PDF hat %2 Seiten. Bitte sicherstellen, dass der Scan vollständig ist.",
        },
        "MaintenanceDialog": {
            "Scan failed: %s": "Scan fehlgeschlagen: %s",
            "Delete %n database entries?": ("%n Datenbankeintrag löschen?", "%n Datenbankeinträge löschen?"),
            "Permanently delete %n files?": ("%n Datei endgültig löschen?", "%n Dateien endgültig löschen?"),
        },
        "MatchWorker": {
            "Analyzing %1 files...": "%1 Dateien werden analysiert...",
            "Matching %1 Scans (Smart Two-Stage)...": "%1 Scans werden abgeglichen (Smart Two-Stage)...",
        },
        "MatchingDialog": {
            "Analysis complete. Found %1 potential scans.": "Analyse abgeschlossen. %1 potenzielle Scans gefunden.",
            "Creating Hybrid PDF: %1...": "Hybrid-PDF wird erstellt: %1...",
            "Merge success: %1": "Zusammenführung erfolgreich: %1",
            "Failed to merge: %1": "Zusammenführung fehlgeschlagen: %1",
            "Triggered import for %1 documents.": "Import für %1 Dokumente angestoßen.",
        },
        "MergeConfirmDialog": {
            "Merge %s documents into a new combined entry?": "%s Dokumente zu einem neuen Eintrag zusammenführen?",
        },
        "OrderCollectionLinker": {
            "Identified %1 collections": "%1 Sammlungen identifiziert",
            "Established %1 new organic process IDs": "%1 neue organische Prozess-IDs erstellt",
            "Linked %1 documents semantically": "%1 Dokumente semantisch verknüpft",
        },
        "ReportEditorWidget": {
            "Report definition '%s' saved.": "Berichtsdefinition '%s' gespeichert.",
        },
        "ReportingWidget": {
            "File is not a Layout (Type: %s)": "Datei ist kein Layout (Typ: %s)",
            "Successfully created ZIP archive with %n documents.": ("ZIP-Archiv mit %n Dokument erfolgreich erstellt.", "ZIP-Archiv mit %n Dokumenten erfolgreich erstellt."),
        },
        "ScannerDialog": {
            "Verbinde mit %s...": "Verbinde mit %s...",
            "Lade Geräteoptionen für %s...": "Lade Geräteoptionen für %s...",
            "Scanne Seite %s von %s...": "Scanne Seite %s von %s...",
            "Scanne Seite %s...": "Scanne Seite %s...",
        },
        "TagManagerDialog": {
            "Updated %n document(s).": ("%n Dokument aktualisiert.", "%n Dokumente aktualisiert."),
            "Merge %s tags into:": "%s Tags zusammenführen in:",
            "Merged tags. Updated %n document(s).": ("Tags zusammengeführt. %n Dokument aktualisiert.", "Tags zusammengeführt. %n Dokumente aktualisiert."),
            "Are you sure you want to remove these %s tags from ALL documents?\n\n%s": "Diese %s Tags wirklich von ALLEN Dokumenten entfernen?\n\n%s",
            "Removed tags from %n document(s).": ("Tags von %n Dokument entfernt.", "Tags von %n Dokumenten entfernt."),
            "Search tags...": "Tags suchen...",
            "Tag Name": "Tag-Name",
            "Usage Count": "Verwendungsanzahl",
        },
        "WorkflowRuleManagerDialog": {
            "A workflow with the name '%1' already exists.": "Ein Ablauf mit dem Namen '%1' existiert bereits.",
            "New Workflow": "Neuer Ablauf",
            "Enter display name:": "Anzeigename eingeben:",
            "Rename Workflow": "Ablauf umbenennen",
            "New display name:": "Neuer Anzeigename:",
            "Delete Failed": "Löschen fehlgeschlagen",
            "Could not delete rule(s): %1": "Regel(n) konnten nicht gelöscht werden: %1",
        },
        "AddTransitionDialog": {
            "e.g. Verify, Approve, Reject": "z.B. Prüfen, Genehmigen, Ablehnen",
            "Label:": "Bezeichnung:",
        },
        "AdvancedFilterWidget": {
            "Show/Hide Editor": "Editor ein-/ausblenden",
        },
        "AuditWindow": {
            "KPaperFlux - Audit and Verification": "KPaperFlux - Prüfung und Verifizierung",
            "Generating comparison document...": "Vergleichsdokument wird erstellt...",
        },
        "BackgroundActivityStatusBar": {
            "Pause Background AI": "Hintergrund-KI pausieren",
            "Stop Background AI": "Hintergrund-KI stoppen",
        },
        "ColumnManagerDialog": {
            "Drag and drop to reorder...": "Ziehen zum Sortieren. Abwählen zum Ausblenden. Doppelklick oder Button zum Entfernen.",
            "Drag and drop to reorder. Uncheck to hide. Double-click or use button to remove dynamic columns.": "Ziehen zum Sortieren. Abwählen zum Ausblenden. Doppelklick oder Button zum Entfernen.",
            "Add Column": "Spalte hinzufügen",
            "Fixed Column": "Feste Spalte",
            "Fixed columns can only be hidden...": "Feste Spalten können nur ausgeblendet, nicht aus dem System entfernt werden.",
            "Fixed columns can only be hidden, not removed from the system.": "Feste Spalten können nur ausgeblendet, nicht aus dem System entfernt werden.",
        },
        "DateRangePicker": {
            "Specific Date": "Bestimmtes Datum",
            "Date Range": "Datumsbereich",
            "Last 90 Days": "Letzte 90 Tage",
            "This Year": "Dieses Jahr",
            "Last Year": "Voriges Jahr",
        },
        "DocumentExporter": {
            "Content": "Inhalt",
            "File Link": "Datei-Link",
        },
        "DocumentListWidget": {
            "Configure Columns...": "Spalten konfigurieren...",
            "Saved Views...": "Gespeicherte Ansichten...",
            "Workflows: %d open · %d done": "Abläufe: %d offen · %d abgeschlossen",
            "No documents to export.": "Keine Dokumente zum Exportieren.",
            "Manual Selection": "Manuelle Auswahl",
        },
        "DuplicateFinderDialog": {
            "Duplicate Finder": "Duplikat-Suche",
            "Potential Duplicates (Sorted by Accuracy):": "Mögliche Duplikate (nach Genauigkeit):",
            "<i>Left: Younger | Right: Older</i>": "<i>Links: Jüngeres | Rechts: Älteres</i>",
            "Keep Left (Delete Old)": "Links behalten (Altes löschen)",
            "Keep Right (Delete Young)": "Rechts behalten (Jüngeres löschen)",
            "Ignore / Next": "Ignorieren / Weiter",
            "No Duplicates": "Keine Duplikate",
            "No duplicates found with current threshold.": "Keine Duplikate mit aktuellem Schwellenwert gefunden.",
        },
        "FilterConditionWidget": {
            "Is True": "Ist wahr",
        },
        "FilterManagerDialog": {
            "Export Item": "Element exportieren",
        },
        "FilterWidget": {
            "Search documents (e.g. 'Amazon 2024 Invoice')...": "Dokumente suchen (z.B. 'Amazon 2024 Rechnung')...",
            "Advanced Criteria": "Erweiterte Kriterien",
            "From:": "Von:",
            "Enable Date": "Datum aktivieren",
            "To:": "Bis:",
            "All": "Alle",
            "Filter anwenden": "Filter anwenden",
        },
        "HybridAssemblerPlugin": {
            "Hybrid Assembler": "Hybrid-Assembler",
            "Assembles hybrid PDFs...": "Erstellt Hybrid-PDFs aus nativen und gescannten Versionen.",
            "Assembles hybrid PDFs from native and scanned versions.": "Erstellt Hybrid-PDFs aus nativen und gescannten Versionen.",
            "Assemble Hybrid PDFs...": "Hybrid-PDFs erstellen...",
        },
        "L10nMarker": {
            "Posteingang": "Posteingang",
            "Warten auf Zahlung": "Warten auf Zahlung",
            "1. Mahnstufe": "1. Mahnstufe",
            "Abgeschlossen": "Abgeschlossen",
            "Inkasso / Recht": "Inkasso / Recht",
            "Monthly summary of all invoices.": "Monatliche Zusammenfassung aller Rechnungen.",
            "Tax Overview (Detailed)": "Steuerübersicht (Detailliert)",
            "In Bearbeitung": "In Bearbeitung",
            "Zu Prüfen (AI Flash)": "Zu Prüfen (AI Flash)",
            "Amazon Käufe": "Amazon Käufe",
            "Versicherungen & Fixkosten": "Versicherungen && Fixkosten",
            "Hohe Beträge (> 500€)": "Hohe Beträge (> 500€)",
            "Gesendet (Outbound)": "Gesendet (Ausgang)",
            "Aktueller Monat": "Aktueller Monat",
            "Letzte 90 Tage": "Letzte 90 Tage",
            "Auto-Tax-Tagging": "Automatisches Steuer-Tagging",
            "Standard-Konfiguration": "Standard-Konfiguration",
        },
        "MainWindow": {
            "KPaperFlux": "KPaperFlux",
            "No documents selected.": "Keine Dokumente ausgewählt.",
            "Current list is empty.": "Aktuelle Liste ist leer.",
            "Plugin Loading Errors...": "Fehler beim Plugin-Laden...",
            "No plugin actions": "Keine Plugin-Aktionen",
            "Please select documents to delete.": "Bitte Dokumente zum Löschen auswählen.",
            "Are you sure you want to delete this item?": "Dieses Element wirklich löschen?",
            "Confirm Delete": "Löschen bestätigen",
            "Deleted": "Gelöscht",
            "Reprocessed": "Neu verarbeitet",
            "Initializing Import...": "Import wird initialisiert...",
            "Importing...": "Wird importiert...",
            "Select Documents": "Dokumente auswählen",
            "PDF Files (*.pdf);;All Files (*)": "PDF-Dateien (*.pdf);;Alle Dateien (*)",
            "Transfer": "Transfer",
            "No compatible files found in transfer folder.": "Keine kompatiblen Dateien im Transfer-Ordner gefunden.",
            "Action required": "Aktion erforderlich",
            "Please select at least one document.": "Bitte mindestens ein Dokument auswählen.",
            "No empty documents found.": "Keine leeren Dokumente gefunden.",
            "Documents merged successfully.": "Dokumente erfolgreich zusammengeführt.",
            "Merge failed.": "Zusammenführung fehlgeschlagen.",
            "KDE Plasma (Detected)": "KDE Plasma (Erkannt)",
            "Not Detected": "Nicht erkannt",
            "About KPaperFlux": "Über KPaperFlux",
            "Please Wait": "Bitte warten",
            "No Duplicates": "Keine Duplikate",
            "No duplicates found with current threshold.": "Keine Duplikate mit aktuellem Schwellenwert gefunden.",
            "Import Dropped Files": "Dateien importieren",
            "Delete source files after import": "Quelldateien nach Import löschen",
            "Import Error": "Importfehler",
            "Import Finished": "Import abgeschlossen",
            "No documents visible to export.": "Keine sichtbaren Dokumente zum Exportieren.",
            "Batch Operation": "Stapel-Operation",
            "Removing stamps is only supported for single documents.": "Stempel entfernen ist nur für einzelne Dokumente möglich.",
            "Stamp removed.": "Stempel entfernt.",
            "Tags Updated": "Tags aktualisiert",
            "Viewing Trash Bin": "Papierkorb anzeigen",
            "Viewing Archive": "Archiv anzeigen",
            "Confirm Global Purge": "Alle Daten löschen bestätigen",
            "DANGER: This will delete ALL documents...": "ACHTUNG: Alle Dokumente, Dateien und Datenbankeinträge werden gelöscht.\n\nDieser Vorgang kann nicht rückgängig gemacht werden.\n\nSind Sie sicher?",
            "System has been reset.": "System wurde zurückgesetzt.",
            "Failed to purge data. Check logs.": "Daten konnten nicht gelöscht werden. Protokoll prüfen.",
            "Document Protected": "Dokument geschützt",
            "This document is a digital original and cannot be restructured.": "Dieses Dokument ist ein digitales Original und kann nicht umstrukturiert werden.",
            "Document deleted (empty structure).": "Dokument gelöscht (leere Struktur).",
            "Pipeline STOPPED due to fatal error.": "Pipeline wegen schwerem Fehler gestoppt.",
            "Orphaned Workflow References": "Verwaiste Ablauf-Referenzen",
            "No orphaned workflow references found. All rule IDs in all documents match a known rule.": "Keine verwaisten Ablauf-Referenzen gefunden. Alle Regel-IDs in allen Dokumenten entsprechen einer bekannten Regel.",
            "Prune Orphaned Workflow References": "Verwaiste Ablauf-Referenzen bereinigen",
            "Prune Orphaned Workflow References...": "Verwaiste Ablauf-Referenzen bereinigen...",
            "Removed orphaned workflow references from %n document(s).": ("Verwaiste Ablauf-Referenz aus %n Dokument entfernt.", "Verwaiste Ablauf-Referenzen aus %n Dokumenten entfernt."),
            "Done": "Fertig",
            "DANGER: This will delete ALL documents, files, and database entries.\n\nThis action cannot be undone.\n\nAre you completely sure you want to reset the system?": "ACHTUNG: Alle Dokumente, Dateien und Datenbankeinträge werden gelöscht.\n\nDieser Vorgang kann nicht rückgängig gemacht werden.\n\nSind Sie sicher?",
        },
        "MaintenanceDialog": {
            "Entries in Database but file missing in Vault:": "Datenbankeinträge ohne Datei im Vault:",
            "Files in Vault but missing in Database:": "Dateien im Vault ohne Datenbankeintrag:",
        },
        "MatchWorker": {
            "Two-Stage Data Preparation (100/150 DPI)...": "Zweistufige Datenvorbereitung (100/150 DPI)...",
        },
        "MatchingDialog": {
            "Hybrid Matching-Dialog": "Hybrid-Abgleich",
            "<b>Hybrid Matching-Dialog</b><br>Finds pairs of scanned and native PDFs in a folder to merge them.": "Hybrid-Abgleich: Findet Paare aus gescannten und nativen PDFs in einem Ordner zum Zusammenführen.",
            "Side-by-side comparison and verification": "Seitenweiser Vergleich und Verifizierung",
            "No folder selected.": "Kein Ordner ausgewählt.",
            "Browse Folder...": "Ordner suchen...",
            "Delete original files after successful merge": "Originaldateien nach Zusammenführung löschen",
            "Scan File": "Scan-Datei",
            "Best Native Match": "Bester nativer Treffer",
            "Start Analysis": "Analyse starten",
            "Start scanning folder or process results": "Ordner scannen oder Ergebnisse verarbeiten",
            "Please select a valid folder first.": "Bitte zuerst einen gültigen Ordner auswählen.",
            "Assembled": "Zusammengesetzt",
            "Match": "Übereinstimmung",
            "Unsure": "Unsicher",
            "View": "Ansehen",
            "Import": "Importieren",
            "Imported ✓": "Importiert ✓",
            "Analyzing...": "Wird analysiert...",
            "Merge Matched": "Übereinstimmende zusammenführen",
            "Import Merged": "Zusammengeführte importieren",
            "Batch Merge": "Stapel-Zusammenführung",
            "No pending matches found to merge.": "Keine ausstehenden Übereinstimmungen gefunden.",
            "Select Output Folder for Hybrid PDFs": "Ausgabeordner für Hybrid-PDFs auswählen",
            "Batch merge complete.": "Stapel-Zusammenführung abgeschlossen.",
            "Hybrid PDF created:": "Hybrid-PDF erstellt:",
            "Import All": "Alle importieren",
            "No assembled documents found to import.": "Keine zusammengesetzten Dokumente zum Importieren gefunden.",
            "Import Error": "Importfehler",
            "Main window not available for standard import.": "Hauptfenster nicht verfügbar.",
        },
        "MergeConfirmDialog": {
            "Confirm Merge": "Zusammenführen bestätigen",
            "Keep original documents": "Originaldokumente behalten",
        },
        "MetadataEditorWidget": {
            "Warning": "Warnung",
            "Semantic data could not be re-validated (%1). Other fields were saved.": "Semantische Daten konnten nicht erneut validiert werden (%1). Andere Felder wurden gespeichert.",
            "Custom Tags: Enter keywords, separated by commas or Enter.": "Eigene Tags: Schlüsselwörter eingeben, mit Komma oder Enter trennen.",
            "Physical Source Components:": "Physische Quell-Komponenten:",
            "Raw Virtual Document Storage:": "Rohdaten des virtuellen Dokuments:",
            "Cached Full Text:": "Zwischengespeicherter Volltext:",
            "No source mapping available.": "Keine Quell-Zuordnung verfügbar.",
            "Incomplete data for GiroCode:\nMissing": "Unvollständige Daten für GiroCode:\nFehlend",
            "Invalid IBAN Checksum!\nCannot generate Payment Code.": "Ungültige IBAN-Prüfsumme!\nZahlungscode kann nicht generiert werden.",
            "QR Library not installed.\nPlease install 'qrcode' package.": "QR-Bibliothek nicht installiert.\nBitte 'qrcode'-Paket installieren.",
            "Invalid Amount format.": "Ungültiges Betragsformat.",
            "Error generating QR:": "Fehler beim QR-Code-Generieren:",
            "Copy Error": "Kopierfehler",
        },
        "OrderCollectionLinker": {
            "Order Collection Linker": "Bestellungs-Sammler",
            "Create Order Collections...": "Bestellungs-Sammlungen erstellen...",
            "Order Collection": "Bestellungs-Sammlung",
            "No document data available to build collections.": "Keine Dokumentdaten zum Erstellen von Sammlungen verfügbar.",
            "Order Collection Discovery Complete:": "Bestellungs-Sammlungen gefunden:",
        },
        "PdfReportGenerator": {
            "Generated: {date}": "Erstellt: {date}",
            "Page {n}": "Seite {n}",
        },
        "PdfViewerWidget": {
            "Previous Hit (Up Arrow)": "Vorheriger Treffer (Pfeil hoch)",
            "Next Hit (Down Arrow)": "Nächster Treffer (Pfeil runter)",
            "Source missing": "Quelle fehlt",
            "Load Error": "Ladefehler",
            "Invalid PDF": "Ungültiges PDF",
            "Empty Doc": "Leeres Dokument",
            "Stitch Error": "Zusammenfüge-Fehler",
        },
        "PieChartWidget": {
            "Others": "Sonstige",
        },
        "ReportEditorWidget": {
            "Numeric Step:": "Numerischer Schritt:",
            "Failed to save report": "Bericht konnte nicht gespeichert werden",
        },
        "ReportingWidget": {
            "Add a text block to the current report": "Textblock zum Bericht hinzufügen",
            "Create a new report": "Neuen Bericht erstellen",
            "Import report style from an exported PDF file": "Berichtsstil aus PDF importieren",
            "Save the current canvas arrangement": "Aktuelle Canvas-Anordnung speichern",
            "Load a saved canvas arrangement": "Gespeicherte Canvas-Anordnung laden",
            "Zoom Level (e.g. 100%)": "Zoom-Stufe (z.B. 100%)",
            "Report style imported and displayed.": "Berichtsstil importiert und angezeigt.",
            "Layout loaded.": "Layout geladen.",
            "Import Successful": "Import erfolgreich",
            "Import Report Style": "Berichtsstil importieren",
            "The report style was successfully imported...": "Der Berichtsstil wurde erfolgreich importiert und der Bibliothek hinzugefügt.",
            "The report style was successfully imported and added to your library.": "Der Berichtsstil wurde erfolgreich importiert und der Bibliothek hinzugefügt.",
            "Could not find an embedded report configuration in this PDF.": "Keine eingebettete Berichtskonfiguration in dieser PDF gefunden.",
            "Please select": "Bitte auswählen",
            "Report Error": "Berichtsfehler",
            "Failed to generate report": "Bericht konnte nicht erstellt werden",
            "No data for table.": "Keine Daten für Tabelle.",
            "Move Up": "Nach oben",
            "Move Down": "Nach unten",
            "Delete Component": "Komponente löschen",
            "Edit Report Definition": "Berichtsdefinition bearbeiten",
            "Enter report name:": "Berichtsname eingeben:",
            "Create Report Definition": "Berichtsdefinition erstellen",
            "No documents found for this report.": "Keine Dokumente für diesen Bericht gefunden.",
            "Export CSV": "CSV exportieren",
            "Export PDF": "PDF exportieren",
            "Successfully exported report to PDF.": "Bericht erfolgreich als PDF exportiert.",
            "Export ZIP": "ZIP exportieren",
            "Successfully created ZIP archive with %d documents.": "ZIP-Archiv mit %d Dokumenten erfolgreich erstellt.",
            "Canvas is empty.": "Canvas ist leer.",
            "Layout saved successfully.": "Layout erfolgreich gespeichert.",
            "Layout loaded successfully.": "Layout erfolgreich geladen.",
            "No valid KPaperFlux payload found.": "Kein gültiges KPaperFlux-Paket gefunden.",
        },
        "RuleManagerWidget": {
            "Rules are integrated into the FilterTree structure.": "Regeln sind in die Filter-Struktur integriert.",
            "Add Tags": "Tags hinzufügen",
            "Add New Rule": "Neue Regel hinzufügen",
            "Apply All Rules to Database": "Alle Regeln auf Datenbank anwenden",
        },
        "SaveListDialog": {
            "Save as List": "Als Liste speichern",
            "List Name:": "Listenname:",
            "My List...": "Meine Liste...",
            "Save Selection Only": "Nur Auswahl speichern",
            "No items selected. Saving all displayed items.": "Keine Auswahl. Alle angezeigten Einträge werden gespeichert.",
            "Please enter a name.": "Bitte einen Namen eingeben.",
        },
        "ScannerDialog": {
            "A4 (210 x 297 mm)": "A4 (210 x 297 mm)",
            "US Letter": "US Letter",
            "US Legal": "US Legal",
            "Maximal": "Maximal",
            "Lange Seite (Standard)": "Lange Seite (Standard)",
            "Kurze Seite (Umblättern)": "Kurze Seite (Umblättern)",
            "Keine Geräte gefunden": "Keine Geräte gefunden",
            "Keine Scanner erkannt.": "Keine Scanner erkannt.",
            "Fehler bei der Suche": "Fehler bei der Suche",
            "Suche fehlgeschlagen": "Suche fehlgeschlagen",
            "Datei fehlt.": "Datei fehlt.",
            "Fehler": "Fehler",
        },
        "SemanticTranslator": {
            "Content": "Inhalt",
            "File Link": "Datei-Link",
            "Posteingang": "Posteingang",
            "Warten auf Zahlung": "Warten auf Zahlung",
            "1. Mahnstufe": "1. Mahnstufe",
            "Abgeschlossen": "Abgeschlossen",
            "Inkasso / Recht": "Inkasso / Recht",
        },
        "SettingsDialog": {
            "Refresh Failed": "Aktualisierung fehlgeschlagen",
            "API returned an empty model list...": "API hat leere Modellliste zurückgegeben. Bitte API-Schlüssel prüfen.",
            "API returned an empty model list. Please check if your API Key has access to Gemini models.": "API hat leere Modellliste zurückgegeben. Bitte prüfen, ob der API-Schlüssel Zugriff auf Gemini-Modelle hat.",
            "Missing Input": "Fehlende Eingabe",
            "Please enter a signature text first.": "Bitte zuerst einen Signaturtext eingeben.",
            "No API Key configured.": "Kein API-Schlüssel konfiguriert.",
            "Analysis Successful": "Analyse erfolgreich",
            "Analysis Failed": "Analyse fehlgeschlagen",
            "AI returned no valid profile.": "KI hat kein gültiges Profil zurückgegeben.",
            "Connected to Ollama, but no models found...": "Mit Ollama verbunden, aber keine Modelle gefunden. Bitte Modell laden (z.B. 'ollama pull llama3').",
            "Connected to Ollama, but no models found. Please pull a model first (e.g., 'ollama pull llama3').": "Mit Ollama verbunden, aber keine Modelle gefunden. Bitte zuerst ein Modell laden (z.B. 'ollama pull llama3').",
            "Could not connect to Ollama": "Verbindung zu Ollama fehlgeschlagen",
            "Log File Missing": "Log-Datei fehlt",
            "The log file has not been created yet.": "Die Log-Datei wurde noch nicht erstellt.",
        },
        "SplitDividerWidget": {
            "Click to Toggle Split": "Klicken zum Trennpunkt umschalten",
        },
        "SplitterDialog": {
            "Hover between pages to find split points...": "Maus zwischen Seiten für Trennpunkte. Schere klicken zum Setzen/Entfernen.",
            "Hover between pages to find split points. Click the scissors to toggle cuts.": "Maus zwischen Seiten für Trennpunkte. Schere klicken zum Setzen/Entfernen.",
            "Cancel Import": "Import abbrechen",
            "Delete this file and abort import.": "Diese Datei löschen und Import abbrechen.",
            "Revert Edits": "Bearbeitungen rückgängig",
            "Step-by-step undo of splits, rotations and deletions.": "Schrittweises Rückgängigmachen von Teilungen, Drehungen und Löschungen.",
            "Import Assistant:": "Import-Assistent:",
            "Abort Import": "Import abbrechen",
            "Import Document": "Dokument importieren",
            "Are you sure you want to delete this document?": "Dieses Dokument wirklich löschen?",
        },
        "SplitterStripWidget": {
            "Rotate selection (90° CW)": "Auswahl drehen (90° im Uhrzeigersinn)",
            "Delete selection": "Auswahl löschen",
            "Reverse sorting (Selection)": "Reihenfolge umkehren (Auswahl)",
            "🛡️ Protected Original: Modification Disabled": "🛡️ Geschütztes Original: Bearbeitung deaktiviert",
            "Invalid Selection": "Ungültige Auswahl",
            "In Import Mode, you can only reverse pages within a single document segment.": "Im Import-Modus nur Seiten innerhalb eines Segments umkehrbar.",
        },
        "TagInputWidget": {
            "Hinzufügen...": "Hinzufügen...",
        },
        "WorkflowDashboardWidget": {
            "Processing: %s": "Verarbeitung: %s",
        },
        "WorkflowGraphWidget": {
            "✓ Apply": "✓ Anwenden",
            "Select a workflow rule to view or edit it.": "Ablauf auswählen, um ihn anzuzeigen oder zu bearbeiten.",
            "Label for the new state:": "Bezeichnung für den neuen Status:",
            "Type:": "Typ:",
            "START — Entry point": "Einstiegspunkt",
            "NORMAL — Intermediate": "Zwischenzustand",
            "END OK — Positive terminal": "Positiver Abschluss",
            "END NOK — Negative terminal": "Negativer Abschluss",
            "END NEUTRAL — Neutral terminal": "Neutraler Abschluss",
            "Missing fields: %s": "Fehlende Felder: %s",
            "Unmet conditions: %s": "Nicht erfüllte Bedingungen: %s",
        },
        "WorkflowManagerWidget": {
            "Process": "Verarbeiten",
            "Processing: %s": "Verarbeitung: %s",
            "Rule Saved & Sanitized": "Regel gespeichert && bereinigt",
            "Rule '%1' saved.\n\n%2 document(s) had their workflow reset to the initial state because their previous state no longer exists in the updated rule.": "Regel '%1' gespeichert.\n\n%2 Dokument(e) wurden auf den Startzustand zurückgesetzt, da ihr vorheriger Zustand in der aktualisierten Regel nicht mehr existiert.",
        },
        "WorkflowProcessingWidget": {
            "Prev": "Zurück",
            "Next": "Weiter",
            "Transition Failed": "Übergang fehlgeschlagen",
            "Could not apply workflow transition: %1": "Ablauf-Übergang konnte nicht angewendet werden: %1",
        },
        "WorkflowRuleCard": {
            "open": "offen",
        },
        "WorkflowSummaryWidget": {
            "No active workflows": "Keine aktiven Abläufe",
            "Click to open this workflow in the Process view": "Klicken, um diesen Ablauf in der Prozessansicht zu öffnen",
            "%n step(s)": ("%n Schritt", "%n Schritte"),
        },

    }

    # DELTA LOGIC: Work on a single tree instance
    tree = tool._get_tree()
    root = tree.getroot()
    modified = False

    def ensure_translation(ctx_node, src, trans):
        nonlocal modified
        # trans can be a str (both numerus forms identical) or (sg, pl) tuple
        sg_trans = trans[0] if isinstance(trans, tuple) else trans
        pl_trans = trans[1] if isinstance(trans, tuple) else trans

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
            t.text = sg_trans
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
            forms = t_node.findall("numerusform")
            expected = [sg_trans, pl_trans]
            actual = [f.text for f in forms]
            if actual != expected or is_unfinished:
                needs_update = True
        else:
            if not t_node.text or is_unfinished or is_vanished or t_node.text != sg_trans:
                needs_update = True

        if needs_update:
            if is_numerus:
                t_node.text = None
                for child in list(t_node): t_node.remove(child)
                nf1 = ET.SubElement(t_node, "numerusform")
                nf1.text = sg_trans
                nf2 = ET.SubElement(t_node, "numerusform")
                nf2.text = pl_trans
            else:
                t_node.text = sg_trans

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
        # Flatten tuple (sg, pl) values to the singular form for shortcut resolution
        res_flat = {src: (t[0] if isinstance(t, tuple) else t) for src, t in res.items()}
        tool.resolve_shortcuts_for_context(ctx_name, reserved=res_flat)

    print("Success: Localization library synchronized (Delta-Safe).")

if __name__ == "__main__":
    fill()
