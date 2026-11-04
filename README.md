# Jarvis-2

Lokaler persönlicher Assistent mit dem vorhandenen 3D-Avatar, LangGraph,
offizieller ChatGPT-Anmeldung und lokaler Piper-Stimme. Separate Kopie von
Jarvis; das Original wurde nicht verändert. Experimentelle Integration, kein
offizielles OpenAI-Produkt und keine Garantie auf Kontozugriff oder Verfügbarkeit.

## Linux: Installation und Start

Python 3.11–3.13 empfohlen, getestet mit Python 3.12. Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv libsndfile1 alsa-utils
git clone https://github.com/mustafauenat-coder/Jarvis-2.git
cd Jarvis-2
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m scripts.download_voice
python -m scripts.test_voice --output jarvis-test.wav
aplay jarvis-test.wav
bash scripts/start.sh
```

Öffne **http://127.0.0.1:8000** im Browser auf demselben Rechner, auf dem
Jarvis läuft. Die offizielle OAuth-Rückleitung ist absichtlich
`http://127.0.0.1:8000/auth/callback`. Daher muss auch der Browser auf diesem
Rechner sein. **GitHub Codespaces und `*.app.github.dev` werden für die
ChatGPT-Anmeldung nicht unterstützt**: Dort zeigt `127.0.0.1` auf den PC des
Nutzers, während der Jarvis-Prozess im entfernten Container läuft. Eine Änderung
der Host-Prüfung oder ein öffentlich sichtbarer Codespaces-Port behebt das nicht.

Für Windows lokal, nachdem Python 3.12 installiert ist:

```powershell
git clone https://github.com/mustafauenat-coder/Jarvis-2.git
cd Jarvis-2
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m scripts.download_voice
python -m scripts.test_voice --output jarvis-test.wav
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Danach **http://127.0.0.1:8000** im selben PC-Browser öffnen. Für Linux später
starten: `cd Jarvis-2 && bash scripts/start.sh`. Beenden mit Ctrl+C. Ein
Serverprozess, keine zusätzlichen Worker. Uvicorn immer mit `--no-access-log`
starten, damit der kurzlebige OAuth-Code nicht in Zugriffslogs landet.

Wenn OpenAI `invalid_grant` zurückgibt, wurde dieser Anmeldecode abgelehnt.
Die Rückleitung entfernt den Code aus der Browseradresse und zeigt, dass die
Anmeldung mit einer frischen Freigabe wiederholt werden muss. Alte Callback-
Adressen nicht erneut laden.

## Erster Verbindungstest

1. **Continue with ChatGPT** anklicken. Der Browser öffnet ausschließlich den
   offiziellen OpenAI-OAuth-Ablauf mit PKCE, dynamischer Registrierung und Consent.
2. Mit dem eigenen berechtigten Konto anmelden und Abo-Nutzung freigeben.
   Falls die Freigabe fehlt: Konto auswählen und **Abo-Nutzung erlauben** klicken.
3. Jarvis lädt den aktuellen Kontokatalog. `gpt-6.1-sol` wird nur vorausgewählt,
   wenn es dort sichtbar ist. Sonst bewusst ein angezeigtes Modell wählen.
   Ein Eintrag im Katalog beweist noch keinen erfolgreichen Inferenzzugriff.
4. **Testantwort erzeugen** anklicken. Dies verbraucht Abo-Kontingent. Erst nach
   `response.completed` werden normaler Chat und Spracheingabe freigeschaltet.
   Die Oberfläche nennt das tatsächlich getestete Modell.
5. **Piper testen** liest „Jarvis ist online.“ lokal vor. Bei aktivierter Stimme
   werden auch Chatantworten vollständig vorgelesen. Keine ElevenLabs- oder
   Browserstimmen-Fallbacks. Fehler bleiben sichtbar.

Nach Serverneustart erneut eine Testantwort erzeugen. Der lokale Teststatus wird
nicht als dauerhafter Beweis für künftigen Modellzugriff gespeichert.

Es gibt **keine API-Key-Konfiguration und keinen kostenpflichtigen API-Fallback**.
OpenAI kann in den Kontoeinstellungen zusätzliche Credits nach dem Planlimit
anbieten. Deaktiviere diese für Jarvis unter
[ChatGPT Usage](https://chatgpt.com/settings/usage), wenn du ausschließlich dein
Abo nutzen möchtest. Jarvis kann diese Kontoeinstellung nicht selbst verifizieren.
Beim Kontingentfehler pausiert Jarvis Anfragen; keine automatischen Wiederholungen.
Nach Prüfung der Limits bewusst **Erneut prüfen** wählen.

## Lokal, offline, Datenschutz

Piper ist nach Paketinstallation und einmaligem Modell-Download offline nutzbar;
der Sprachtest stellt keinerlei Netzwerkverbindung her. Es fallen keine
Sprachdienstgebühren an; Hardware, Strom und ggf. Server bleiben eigene Kosten.
ChatGPT braucht Internet. Browser-Spracherkennung kann Audio an den Browseranbieter
senden und ist **nicht** als offline implementiert. Verlauf bleibt im aktuellen
Tab und wird als Kontext an OpenAI übermittelt (maximal zehn vorige Gesprächspaare).
Kein dauerhaftes Gedächtnis. Optionale Wikipedia-Recherche nutzt Internet.

Anmeldung unter `${XDG_CONFIG_HOME:-$HOME/.config}/jarvis-2/accounts.json`,
Unix-Verzeichnisrechte 0700, Datei 0600, atomare Speicherung. Modelle unter
demselben Verzeichnis in `voices/`. Keine Tokens in Repo, Browser-Speicher oder
Serverzugriffslogs. Das ist lokale Dateisicherung, keine Verschlüsselung gegen
andere Programme unter demselben Betriebssystemkonto. Windows-Nutzer müssen die
Zugriffsrechte ihres Benutzerprofils schützen; die Linux-Rechte gelten dort nicht.

Mehrere Kontoregistrierungen bleiben getrennt; Auswahl + erneute Anmeldung
aktiviert ein Konto. Abmelden versucht den Refresh-Token zu widerrufen und löscht
lokale Tokens. Bei fehlender Bestätigung zusätzlich in ChatGPT trennen. Issued
Client-ID und Host-ID bleiben für erneute Anmeldung erhalten.

Der Server bindet nur 127.0.0.1, prüft Host und POST-Origin und ist **kein öffentlicher
Mehrbenutzerdienst**. Für einen eigenen Linux-Server ist ein privater SSH-Tunnel
möglich: `ssh -N -L 8000:127.0.0.1:8000 USER@SERVER`, danach denselben lokalen Link
öffnen. SSH-Zugriff und Portkonflikte selbst einrichten. Codespaces-Portfreigabe
und öffentliches Hosting werden von diesem lokalen Login-Aufbau nicht unterstützt.

## Stimmenmodell und Lizenz

Jarvis-2: GPL-3.0-or-later (siehe LICENSE). Piper 1.8.0:
GPL-3.0-or-later. Modellverteilung separat, kein ONNX-Binary im Git-Repository.
`scripts.download_voice` lädt ONNX, JSON-Konfiguration und Modellkarte aus
`rhasspy/piper-voices`, festgelegt auf Revision
`e7229f7d33a10e145e109b886d661984201ac3c4` und protokolliert SHA-256-Werte lokal.
Diese Hashwerte sind Download-Nachweise, keine unabhängige Herkunftsprüfung.

Der Modellkatalog deklariert MIT, die konkrete Thorsten-high-Modellkarte nennt
CC0 für den Datensatz und Fine-Tuning von Lessac high. Eine eigene Modelllizenz
steht nicht in dieser Einzelkarte; deshalb Kataloglizenz und Dataset-Lizenz
getrennt dokumentiert. Quellen und Lizenzhinweise in [THIRD_PARTY.md](THIRD_PARTY.md).
Bei Weitergabe von Piper-Binaries auch entsprechende GPL-Quellcodepflichten
erfüllen; dieser Quellcode-Release verweist auf den Paketbezug und bündelt keine
Piper-Binaries oder Stimmenmodelle.

## Tests und Grenzen

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Automatisierte Tests verwenden simulierte OpenAI-Antworten; sie bestätigen keinen
realen Kontozugriff. Den tatsächlichen Login, Consent, Modellzugriff und
Sprachaufnahme mit eigenem Konto/Browser prüfen. Ergebnisstand in TEST_RESULTS.md.

Implementiert nach [OpenAI OSS-Anleitung](https://developers.openai.com/siwc/token-sharing-open-source),
[Login](https://developers.openai.com/siwc/token-sharing-open-source/sign-in),
[Modelle](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference),
[Preview-Grenzen](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).
Nur öffentlicher `/v1/models`-Katalog und `/v1/responses` mit `store:false, stream:true`.
Keine internen ChatGPT-Endpunkte, kein Auslesen bestehender ChatGPT-/Codex-Sitzungen.
