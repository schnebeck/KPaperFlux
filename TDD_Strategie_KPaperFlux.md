# **TDD-Strategie: KPaperFlux**

**Framework:** pytest, pytest-qt, unittest.mock

## **1\. Philosophie: Red-Green-Refactor**

Es wird **kein Produktionscode** geschrieben, solange kein Test existiert, der diesen Code benötigt und fehlschlägt.

1. **RED:** Schreibe einen Test für das Feature. Er muss fehlschlagen (AssertionError oder ImportError).  
2. **GREEN:** Implementiere den Code minimalistisch, bis der Test besteht.  
3. **REFACTOR:** Optimiere den Code, ohne das Verhalten zu ändern.

## **2\. Architektur (MVC Pattern)**

### **Model (Logik \-\> Unit Tests)**

* **Klassen:** DocumentVault, PipelineProcessor, DatabaseManager.  
* **Test-Fokus:** Datenintegrität, Dateisystem-Operationen, SQL-Logik.  
* **Hardware:** Scanner und Google API werden hier immer gemockt.

### **Controller (Ablauf \-\> Mock Tests)**

* **Klassen:** ScanWorkflowController, SearchController.  
* **Test-Fokus:** Reagiert der Controller korrekt auf den Button? Ruft er das Model auf?  
* **Mocking:** Die View und das Model werden gemockt, um nur den Ablauf zu testen.

### **View (GUI \-\> pytest-qt)**

* **Klassen:** MainWindow, ResultListWidget.  
* **Test-Fokus:** Existieren die Buttons? Sind Signale verbunden?  
* **Werkzeug:** pytest-qt (qtbot) simuliert User-Interaktionen.

## **3\. Mocking-Regeln**

### **Scanner (SANE)**

Tests dürfen niemals versuchen, auf echte Hardware zuzugreifen.

* Nutze unittest.mock.patch('sane.init') oder Wrapper-Klassen.  
* Simuliere Scan-Ergebnisse durch Laden von Test-Bildern aus tests/assets/.

### **Google AI**

Tests dürfen keine Kosten verursachen und kein Netzwerk benötigen.

* Mocke die Antwort von generativeai.GenerativeModel.generate\_content.  
* Liefere statische JSON-Antworten für Tests zurück.

## **4\. Ordnerstruktur**

KPaperFlux/  
├── core/           \# Geschäftslogik  
├── gui/            \# PyQt Fenster  
└── tests/  
    ├── unit/       \# Schnelle Tests (Model/Controller)  
    ├── integration/\# Tests mit echter DB (in /tmp)  
    └── gui/        \# Tests mit UI-Elementen  
