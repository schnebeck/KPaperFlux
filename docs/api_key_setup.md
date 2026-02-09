# Einrichtung des Google Gemini API-Keys

Diese Anleitung beschreibt Schritt für Schritt, wie Sie einen API-Key für KPaperFlux generieren.

## Schritt 1: Google AI Studio aufrufen

Öffnen Sie die Webseite [Google AI Studio](https://aistudio.google.com/) in Ihrem Browser.

## Schritt 2: Anmelden

Klicken Sie auf **"Sign in to Google AI Studio"** und melden Sie sich mit Ihrem Google-Konto an.

## Schritt 3: API-Key Bereich öffnen

1. Klicken Sie im linken Menü auf **"Get API key"**.
2. Klicken Sie auf den blauen Button **"Create API key"**.

## Schritt 4: Projekt auswählen

Wenn Sie gefragt werden, wählen Sie entweder ein bestehendes Google Cloud Projekt aus oder klicken Sie auf **"Create API key in new project"**.

## Schritt 5: Key kopieren

Der neue API-Key wird angezeigt. Klicken Sie auf das **Kopieren-Symbol** neben dem Key.
*Achtung: Teilen Sie diesen Key niemanden.*

## Schritt 6: Key in KPaperFlux nutzen

Öffnen Sie Ihr Terminal im KPaperFlux Projektordner und setzen Sie den Key als Umgebungsvariable:

**Linux/Mac:**
```bash
export GEMINI_API_KEY="Ihr_Kopierter_Key_Hier"
```

Starten Sie danach die Anwendung:
```bash
python main.py
```

Der Key ist nur für die aktuelle Terminal-Sitzung gültig. Um ihn dauerhaft zu speichern, fügen Sie die Export-Zeile in Ihre `~/.bashrc` oder `~/.zshrc` ein.
