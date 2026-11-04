# Drittanbieter und Lizenzen – geprüft am 4. November 2026

* Piper 1.8.0: **GPL-3.0-or-later** laut [setup.py](https://github.com/OHF-Voice/piper1-gpl/blob/main/setup.py).
  [Quellcode](https://github.com/OHF-Voice/piper1-gpl),
  [Lizenztext](https://github.com/OHF-Voice/piper1-gpl/blob/main/COPYING),
  [Python-API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md).
* Stimmenkatalog `rhasspy/piper-voices`: **MIT** laut
  [Repository-Metadaten](https://huggingface.co/rhasspy/piper-voices/blob/e7229f7d33a10e145e109b886d661984201ac3c4/README.md).
* `de_DE-thorsten-high`: deutsche Einzelstimme, 22.050 Hz. Die
  [Modellkarte](https://huggingface.co/rhasspy/piper-voices/blob/e7229f7d33a10e145e109b886d661984201ac3c4/de/de_DE/thorsten/high/MODEL_CARD)
  nennt **CC0 für den Datensatz**, keine separate Modelllizenz. Fine-Tuning von
  Lessac high wird ausdrücklich erwähnt. [Thorsten-Datensatz](https://github.com/thorstenMueller/Thorsten-Voice).

Stimme nicht im Repository eingebettet; Nutzer laden die festgelegte Revision
mit `python -m scripts.download_voice` herunter. Die Originalmodellkarte liegt
anschließend neben dem Modell. Bei eigener Weiterverteilung von Modellen oder
fertigen Installationspaketen die jeweiligen Lizenztexte und Hinweise beilegen.

Die übrigen Python-Abhängigkeiten werden über pip bezogen. Ihre eigenen Lizenzen
gelten weiter. Dieser Release enthält eigenen Anwendungscode und den GPL-Text;
er enthält keine fremden Python-Paketbinaries. Keine OpenAI-Markenrechte übertragen.
