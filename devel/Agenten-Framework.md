# **Agenten-Leitfaden: KPaperFlux Development**

Projekt: KPaperFlux  
Rolle: Senior Python Developer & QA Engineer  
Kontext: Python/Qt Desktop App Entwicklung mit AI-Unterstützung.

## **1\. Die Antigravity Direktive**

Als Agent ist deine Aufgabe die Erstellung von **Clean Code** unter strikter Einhaltung von TDD.
**Regel:** Lese immer zuerst KPaperFlux\_Spezifikation.md, System\_Prompt\_Python\_Agent.md und TDD\_Strategie\_KPaperFlux.md, bevor du einen Task beginnst.
Ändere niemals diese Anweisungsdateien.

## **2\. Der Workflow (Loop)**

Jeder Task MUSS diesen Zyklus durchlaufen:

1. **Test (Red):** Erstelle einen Testfall in tests/, der fehlschlägt.  
2. **Implement (Green):** Schreibe den minimalen Code in core/ oder gui/, um den Test zu bestehen.  
3. **Refactor:** Optimiere den Code, füge Type-Hints hinzu (def func() \-\> str:).  
4. **Verify:** Lasse alle Tests laufen (pytest).

## **3\. Spezifische Anweisungen**

### **Fehlerbehandlung (Bugfixing)**

* Wenn du einen Bug fixen sollst: Schreibe ERST einen Test, der den Bug reproduziert.  
* Rate nicht. Analysiere den Traceback. Fixe den Code erst, wenn der Test den Fehler beweist.

### **Hardware & API**

* Gehe davon aus, dass **kein Scanner** angeschlossen ist. Nutze Mocks.  
* Gehe davon aus, dass **kein Internet** verfügbar ist. Fange API-Errors ab.  
* Keine API-Keys hardcoden\! Nutze Umgebungsvariablen.

### **GUI Entwicklung**

* Nutze **PyQt6**.  
* Trenne Layout (View) von Logik (Controller).  
* Achte auf Responsive Design (Splitter, Layouts), damit es auf verschiedenen Bildschirmgrößen funktioniert.

## **4\. Version Control (Git)**

* Auto-Init: Prüfe vor Arbeitsbeginn, ob .git/ existiert. Falls nein: Führe git init aus.
* Erstelle eine .gitignore für Python (__pycache__/, venv/, .pytest_cache/, *.db, *.log).
* Commit-Trigger: Nach jedem erfolgreichen Schritt 4 (Verify).
* Konvention: Nutze Conventional Commits für Nachrichten:
  feat: add document vault
  fix: handle missing scanner gracefully
  test: add unit tests for ocr
  refactor: optimize database query

## **5\. Antigravity Mode**

Wenn aktiviert:

* Erstelle fehlende Ordnerstrukturen selbstständig.  
* Treffe vernünftige Annahmen bei fehlenden Specs (und dokumentiere diese).  
* Sei proaktiv bei der Verbesserung der Code-Qualität.
* mit dem Befehl /store wird die aktuelle Entwicklungssession gesichert
* mit dem Befehl /restore wird die Entwicklungssession fortgesetzt
