# Prüfstand 4. November 2026

Getestet unter Windows mit Python 3.12.16 und Chrome. Linux/WSL ist auf diesem
Rechner nicht installiert; die Linux-Befehle sind vorbereitet, hier nicht ausgeführt.

* 16 pytest-Tests bestanden. Davon 15 mit simuliertem OpenAI-Dienst und ein echter
  Piper-Offlinetest, bei dem Python-Netzwerkverbindungen explizit gesperrt wurden.
* Signierte Test-ID-Tokens: PKCE, Nonce, Audience, Replay, abgelehnter Consent,
  Kontowechsel-Mismatch, fehlender Scope, Refresh und Abmelden geprüft.
* Kontokatalogfilter, Modellfreigabe erst nach Test, unvollständige/fehlgeschlagene
  Streams, Kontingentpause und fehlender kostenpflichtiger Fallback geprüft.
* Origin-/Host-Prüfung und fehlendes Stimmenmodell geprüft.
* Echte `de_DE-thorsten-high`-WAV-Datei mit „Jarvis ist online.“ erzeugt.
* Browserprüfung bestanden: echtes lokales WAV abgespielt, Anmeldung erforderlich,
  simulierte Modellauswahl und Testantwort, Chat, Zurücksetzen, Desktop und Mobil
  ohne horizontalen Überlauf; keine JavaScript-Fehler.

Diese Tests sind kein Nachweis eines erfolgreichen echten ChatGPT-Logins oder
eines freigeschalteten GPT-6.1-Sol-Kontos. Dafür muss der Nutzer die OpenAI-Anmeldung
und Abo-Freigabe persönlich abschließen. Die Anwendung zeigt danach den echten
Kontokatalog und nennt erst nach erfolgreicher Testantwort das verwendete Modell.
Auch die reale Mikrofonaufnahme erfordert die Freigabe im jeweiligen Browser.

Der erste Live-Login endete mit `invalid_grant`. Ursache nicht abschließend
ermittelt. Fehlerbehandlung hält nun die unbestätigte dynamische Client-ID getrennt
von verifizierten Konten fest und erlaubt frische Autorisierung mit neuem PKCE-
Wert. Für OAuth muss die App lokal auf demselben Rechner wie der Browser laufen;
Codespaces kann die Loopback-Rückleitung nicht empfangen.
