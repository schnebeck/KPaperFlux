
import xml.etree.ElementTree as ET
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
TS_FILE = os.path.join(PROJECT_ROOT, 'resources/l10n/de/gui_strings.ts')

TRANSLATIONS = {
    "Delete Document": "Dokument löschen",
    "Archive Document": "Dokument archivieren",
    "Restore from Archive": "Aus Archiv wiederherstellen",
    "Restored from Archive": "Aus Archiv wiederhergestellt",
    "Changes are applied automatically when 'Filter active' is checked.": "Änderungen werden automatisch angewendet, wenn 'Filter aktiv' aktiviert ist.",
    "ID": "ID",
    "Imported Date": "Importdatum",
    "Used Date": "Zuletzt benutzt",
    "Deleted Date": "Löschdatum",
    "Locked Date": "Sperrdatum",
    "Autoprocessed Date": "Verarbeitet",
    "Exported Date": "Exportiert",
    "Status": "Status",
    "Typ - Tags": "System-Tags",
    "Tags": "Tags",
    "Date": "Datum",
    "Classification": "Klassifizierung",
    "Workflow Step": "Workflow-Schritt",
    "Full Text": "Volltext",
    "Direction": "Richtung",
    "Context": "Mandant",
    "AI Confidence": "KI-Konfidenz",
    "AI Reasoning": "KI-Begründung",
    "Stamp Text (Total)": "Stempeltext (Gesamt)",
    "Stamp Type": "Stempeltyp",
    "Audit Mode": "Audit-Modus",
    "In Trash": "Im Papierkorb",
    "Archived": "Archiviert",
}

NUMERUS_TRANSLATIONS = {
    "Delete %n Document(s)": ["%n Dokument löschen", "%n Dokumente löschen"],
    "Archive %n Document(s)": ["%n Dokument archivieren", "%n Dokumente archivieren"],
    "Restore %n Document(s) from Archive": ["%n Dokument aus Archiv wiederherstellen", "%n Dokumente aus Archiv wiederherstellen"],
    "Archived %n document(s)": ["%n Dokument archiviert", "%n Dokumente archiviert"],
    "Restored %n document(s) from Archive": ["%n Dokument aus Archiv wiederhergestellt", "%n Dokumente aus Archiv wiederhergestellt"],
    "Contains %n item(s).": ["%n Element enthalten.", "%n Elemente enthalten."],
    "Contains <b>%n</b> documents.": ["Enthält <b>%n</b> Dokument.", "Enthält <b>%n</b> Dokumente."],
    "and %n more.": ["und %n weiteres.", "und %n weitere."],
    "Delete %n selected item(s)?": ["%n ausgewähltes Element löschen?", "%n ausgewählte Elemente löschen?"],
    "Import Assistant: Batch (%n file(s))": ["Import-Assistent: Batch (%n Datei)", "Import-Assistent: Batch (%n Dateien)"],
    "Import and Split into %n Part(s)": ["Importieren und in %n Teil aufteilen", "Importieren und in %n Teile aufteilen"],
    "Save and Split into %n Part(s)": ["Speichern und in %n Teil aufteilen", "Speichern und in %n Teile aufteilen"],
    "Are you sure you want to delete %n selected rule(s)?": ["Sind Sie sicher, dass Sie %n ausgewählte Regel löschen möchten?", "Sind Sie sicher, dass Sie %n ausgewählte Regeln löschen möchten?"],
}

def fill():
    if not os.path.exists(TS_FILE):
        print(f"Error: {TS_FILE} not found.")
        return

    tree = ET.parse(TS_FILE)
    root = tree.getroot()
    
    modified = False
    for context in root.findall('context'):
        for msg in context.findall('message'):
            src = msg.find('source')
            if src is None or not src.text: continue
            
            trans = msg.find('translation')
            if trans is None: continue
            
            # 1. Simple strings
            if src.text in TRANSLATIONS:
                if not trans.text or trans.get('type') == 'unfinished':
                    trans.text = TRANSLATIONS[src.text]
                    if 'type' in trans.attrib:
                        del trans.attrib['type']
                    modified = True
                    print(f"Fixed: {src.text} -> {TRANSLATIONS[src.text]}")
                
            # 2. Plural forms
            if src.text in NUMERUS_TRANSLATIONS:
                msg.set('numerus', 'yes')
                forms = trans.findall('numerusform')
                target_forms = NUMERUS_TRANSLATIONS[src.text]
                
                if not forms:
                    # Clear any text if it was a simple translation before
                    trans.text = None 
                    for form_text in target_forms:
                        f = ET.SubElement(trans, 'numerusform')
                        f.text = form_text
                else:
                    for i, form_text in enumerate(target_forms):
                        if i < len(forms):
                            forms[i].text = form_text
                
                if 'type' in trans.attrib:
                    del trans.attrib['type']
                modified = True
                print(f"Fixed Plural: {src.text}")

            # 3. Clean up unfinished strings that ALREADY have a translation
            if trans.text and trans.get('type') == 'unfinished':
                del trans.attrib['type']
                modified = True
                print(f"Finished: {src.text}")

    if modified:
        # Standard XML write doesn't do pretty-print, but sync_translations will fix indentation
        tree.write(TS_FILE, encoding='utf-8', xml_declaration=True)
        print("Writing changes. Running sync_translations.py to re-indent...")
        
        # Run sync_translations.py to restore pretty indentation
        os.system(f"python3 {os.path.join(PROJECT_ROOT, 'scripts/sync_translations.py')}")

if __name__ == "__main__":
    fill()
