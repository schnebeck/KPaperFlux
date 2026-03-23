
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
        "Really delete %s duplicates?": "Wirklich %s Dubletten löschen?",
        "%s documents could not be deleted.": "%s Dokumente konnten nicht gelöscht werden.",
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
            "%s error(s) occurred during reprocessing. Check logs.": "%s Fehler bei der Verarbeitung. Bitte Protokoll prüfen.",
            "Importing %s/%s: %s": "Importiere %s/%s: %s",
            "Found %s files in transfer folder. Do you want to import them now?": "%s Dateien im Transfer-Ordner gefunden. Jetzt importieren?",
            "Queued %s docs for extraction.": "%s Dokumente für Extraktion vorgemerkt.",
            "Start semantic extraction for %s documents without details?": "Semantische Extraktion für %s Dokumente ohne Details starten?",
            "Merge error: %s": "Zusammenführungsfehler: %s",
            "<h3>KPaperFlux v1.0</h3><p>A modern document management tool.</p><hr><p><b>Qt Version:</b> %1</p><p><b>Python:</b> %2</p><p><b>System:</b> %3</p><p><b>Desktop Environment:</b> %4</p>": "<h3>KPaperFlux v1.0</h3><p>Modernes Dokumentenmanagementsystem.</p><hr><p><b>Qt-Version:</b> %1</p><p><b>Python:</b> %2</p><p><b>System:</b> %3</p><p><b>Desktopumgebung:</b> %4</p>",
            "Comparing documents (%s/%s)...": "Dokumente werden verglichen (%s/%s)...",
            "Imported %s documents.\nBackground processing started.": "%s Dokumente importiert.\nHintergrundverarbeitung gestartet.",
            "Could not locate physical file for UUID: %s": "Physische Datei für UUID nicht gefunden: %s",
            "Stamp applied to %s document(s).": "Stempel auf %s Dokument(e) angewendet.",
            "Stamping operation failed: %s": "Stempel-Operation fehlgeschlagen: %s",
            "Updated tags for %s documents.": "Tags für %s Dokumente aktualisiert.",
            "Restored %s document(s).": "%s Dokument(e) wiederhergestellt.",
            "Permanently deleted %s document(s).": "%s Dokument(e) endgültig gelöscht.",
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
        "WorkflowRuleFormEditor": {
            "Rule Name:": "Name des Ablaufs:",
            "Description:": "Beschreibung:",
            "Regex Triggers:": "Regex Auslöser:",
            "Enter rule name...": "Ablaufname eingeben...",
            "What does this rule do?": "Was macht dieser Ablauf?",
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
            "%s document(s) are locked and cannot be deleted.": "%s Dokument(e) sind gesperrt und können nicht gelöscht werden.",
            "Are you sure you want to permanently delete %s document(s)?\nThis cannot be undone.": "%s Dokument(e) wirklich endgültig löschen?\nDieser Vorgang kann nicht rückgängig gemacht werden.",
        },
        "ColumnManagerDialog": {
            "%s (Fixed)": "%s (Fest)",
        },
        "ExportDialog": {
            "Exporting %s documents.": "%s Dokumente werden exportiert.",
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
            "Delete %s database entries?": "%s Datenbankeinträge löschen?",
            "Permanently delete %s files?": "%s Dateien endgültig löschen?",
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
        },
        "ScannerDialog": {
            "Verbinde mit %s...": "Verbinde mit %s...",
            "Lade Geräteoptionen für %s...": "Lade Geräteoptionen für %s...",
            "Scanne Seite %s von %s...": "Scanne Seite %s von %s...",
            "Scanne Seite %s...": "Scanne Seite %s...",
        },
        "TagManagerDialog": {
            "Updated %s document(s).": "%s Dokument(e) aktualisiert.",
            "Merge %s tags into:": "%s Tags zusammenführen in:",
            "Merged tags. Updated %s document(s).": "Tags zusammengeführt. %s Dokument(e) aktualisiert.",
            "Are you sure you want to remove these %s tags from ALL documents?\n\n%s": "Diese %s Tags wirklich von ALLEN Dokumenten entfernen?\n\n%s",
            "Removed tags from %s document(s).": "Tags von %s Dokument(e) entfernt.",
        },
        "WorkflowRuleManagerDialog": {
            "A workflow with the name '%1' already exists.": "Ein Ablauf mit dem Namen '%1' existiert bereits.",
        },

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
