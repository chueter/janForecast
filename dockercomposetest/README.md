# CapEx Forecast Assistant: Betrieb und Transfer

Diese Anleitung beschreibt den Prototyp im Verzeichnis `dockercomposetest/`: seine Container und Datenflüsse, den Umzug auf einen anderen Rechner mit Docker Compose und die wichtigsten Diagnose- und Neustartbefehle. Die Befehle sind für PowerShell formuliert und werden aus `dockercomposetest/` ausgeführt.

## 1. Architektur des Prototyps

### Überblick

Es gibt zwei Browser-Oberflächen. Die CapEx-GUI auf Port 8501 führt eine Analyse mit hochgeladenen CSV- und PDF-Dateien aus. Open WebUI auf Port 3000 ist eine separate allgemeine Chat-Oberfläche für Ollama. Beide sprechen den Ollama-Dienst im internen Compose-Netzwerk an. Der Browser greift **nicht direkt** auf Ollamas Port 11434 zu.

```text
                         Docker-Host / Browser
                  +----------------+  +----------------+
                  | CapEx-GUI      |  | Open WebUI     |
                  | localhost:8501 |  | localhost:3000 |
                  +-------+--------+  +--------+-------+
                          |                    |
+-------------------------|--------------------|----------------------+
| Docker Compose network  |                    |                      |
|                         v                    v                      |
|  +----------------------+---+       +--------+---------+            |
|  | capex-app (FastAPI)       |------>| ollama           |            |
|  | HTML, CSV/PDF, API        |       | LLM + embeddings |            |
|  | Chroma EphemeralClient    |       | port 11434       |            |
|  +--------------------------+        +--------+---------+            |
|                                                  ^                   |
|  +--------------------------+                    |                  |
|  | ollama-models            |--------------------+                  |
|  | one-shot model download  |        ollama pull                    |
|  +--------------------------+                                       |
+----------------------------------------------------------------------+

Chroma laeuft innerhalb von capex-app, nicht als eigener Container.
```

### Dienste und Images

| Compose-Dienst | Image / Build | Aufgabe | Host-Port |
|---|---|---|---|
| `ollama` | `ollama/ollama:latest` | Stellt Chat- und Embedding-Modelle per Ollama-API bereit und kann die NVIDIA-GPU verwenden. | Nicht veröffentlicht; nur intern auf `11434` |
| `ollama-models` | `ollama/ollama:latest` | Einmaliger Setup-Container. Wartet auf Ollama und lädt das konfigurierte LLM sowie `nomic-embed-text`. Beendet sich danach erfolgreich. | keiner |
| `open-webui` | `ghcr.io/open-webui/open-webui:main` | Allgemeine Chat-Oberfläche für Ollama, unabhängig von der CapEx-GUI. | `127.0.0.1:3000` |
| `capex-app` | lokal aus `Dockerfile` gebaut | FastAPI, statische CapEx-GUI, Dateiannahme, CSV-Verarbeitung, PDF-RAG und API-Dokumentation. | `127.0.0.1:8501` |

Die Image-Namen `latest` und `main` sind veränderlich. Dadurch kann ein Neubau oder Pull später andere Programmversionen liefern. Für einen länger betriebenen Firmenprototyp sollten die Image-Versionen fest gepinnt werden.

### Was passiert bei einer CapEx-Anfrage?

```text
Browser              capex-app              Ollama / Qwen       Chroma
  |                     |                         |                 |
  | Dateien + Frage     |                         |                 |
  |-------------------->|                         |                 |
  |                     |                         |                 |
  |                     | CSV-only, klare Summe:  |                 |
  |                     | Pandas berechnet direkt |                 |
  |                     |                         |                 |
  |                     | CSV-only, freie Frage:  |                 |
  |                     | Prompt mit CSV + Verlauf|                 |
  |                     |------------------------>|                 |
  |                     |<------------------------| Antwort         |
  |                     |                         |                 |
  |                     | PDF: nomic erzeugt      |                 |
  |                     | Embeddings              |                 |
  |                     |------------------------- Chunks + Vektoren>
  |                     |<------------------------- Treffer         |
  |                     | Frage + Treffer         |                 |
  |                     |------------------------>|                 |
  |                     |<------------------------| Antwort         |
  |                     | Collection loeschen     |                 |
  |<--------------------|                         |                 |
  | Antwort             | temporaere Dateien weg  |                 |
```

Die API lässt nur eine Forecast-Verarbeitung gleichzeitig laufen. Uploads sind auf zehn Dateien, 20 MB je Datei und 50 MB Gesamtgröße begrenzt. Der Browser sendet bei jeder Folgefrage die ausgewählten Dateien erneut und hält den Chatverlauf lokal im Tab; dadurch werden PDFs pro Folgefrage erneut gelesen und indexiert.

### Container, flüchtige Daten und persistierte Daten

| Komponente / Daten | Wo? | Lebensdauer |
|---|---|---|
| Ollama-Server und Modellrunner | Container `ollama` | Container läuft dauerhaft; ein Modell wird bei einer Anfrage geladen und normalerweise nach Ollamas Keep-alive-Zeit wieder entladen. |
| Modell-Dateien für Qwen und Nomic | Named Volume `ollama_data` unter `/root/.ollama` | Bleiben über Container-Neustarts und normale `docker compose down`-Aufrufe hinweg erhalten. |
| Modell-Downloader | Kurzlebiger Container `ollama-models` | Lädt Modelle und beendet sich mit Exit-Code 0. Ein beendeter Zustand ist hier normal. |
| Open-WebUI-Konten, Chats und Einstellungen | Named Volume `open-webui_data` unter `/app/backend/data` | Bleiben über Container-Neustarts erhalten. |
| CapEx-Webcode und Tests | Bind-Mounts `./src:/app/src` und `./tests:/app/tests` | Dateien liegen im Projektverzeichnis auf dem Host. Änderungen an Python-Code benötigen einen App-Neustart, aber keinen Image-Neubau. |
| App-Datenverzeichnis | Bind-Mount `./data:/app/data` | Host-Verzeichnis bleibt erhalten. Der aktuelle Code schreibt dort keine Uploads oder Chroma-Indizes ab. |
| Hochgeladene Dokumente | `TemporaryDirectory` im `capex-app`-Container | Existieren nur während der Anfrage und werden danach entfernt. |
| Chroma-Collection und PDF-Chunks | `chromadb.EphemeralClient()` im Python-Prozess | Eine pro Anfrage eindeutig benannte Collection; sie wird nach der Antwort gelöscht. Es gibt keinen Chroma-Container und keine dauerhafte Vektordatenbank. |
| Embeddings und Antwort | Arbeitsspeicher während der Anfrage | Embeddings werden pro PDF-Anfrage erzeugt; Antworttext wird an den Browser zurückgegeben. |
| Chat der CapEx-GUI | Browser-Tab | Nicht serverseitig persistiert; ein neuer Tab oder geleerter Chat verliert den Verlauf. Open-WebUI-Chats dagegen liegen im Open-WebUI-Volume. |

`docker compose down -v` löscht **beide Named Volumes** und damit heruntergeladene Ollama-Modelle sowie Open-WebUI-Daten. Diesen Befehl nur ausführen, wenn dieser Datenverlust gewünscht ist.

### Modell- und Rechenpfade

- Standard-LLM: `qwen2.5:14b`; Standard-Kontextfenster: 4096 Tokens.
- Embedding-Modell für PDFs: `nomic-embed-text`.
- CSV: eindeutige Summenfragen mit Jahr und Kategorie werden direkt aus numerischen CSV-Spalten berechnet. Andere CSV-Fragen werden als Textkontext an Qwen gegeben.
- PDF: Text wird mit LlamaIndex ausgelesen, eingebettet, temporär in Chroma gespeichert und relevant abgerufen. Qwen formuliert daraus die Antwort.
- Open WebUI ist kein RAG-Ersatz für die CapEx-GUI: Es chattet direkt mit Ollama und verwendet die von Open WebUI konfigurierten Funktionen/Modelle.

## 2. Transfer auf einen Rechner mit Docker Compose und RTX 16 GB

### Voraussetzungen am Zielrechner

1. Windows 11 mit aktuellem NVIDIA-Treiber und Docker Desktop mit WSL2, oder ein unterstütztes Linux-System mit NVIDIA-Treiber und NVIDIA Container Toolkit.
2. Docker Compose v2 (`docker compose`, nicht das alte separate `docker-compose`).
3. NVIDIA RTX mit 16 GB VRAM, mindestens 32 GB Systemspeicher empfohlen, ausreichend freier Plattenplatz für Images und Modelle.
4. Zugriff auf Docker Hub und GitHub Container Registry. Beim ersten Start werden Images und mehrere GB an Modell-Dateien heruntergeladen. Open WebUI kann außerdem beim ersten Start sein eigenes Embedding-Modell von Hugging Face herunterladen.

Auf Docker Desktop/Windows muss GPU-Unterstützung in WSL2 verfügbar sein. Auf Linux muss Docker den NVIDIA-Treiber sehen. Wenn Ollama nur CPU meldet, zuerst die GPU-Konfiguration des Hosts und Docker prüfen; die Compose-Datei reserviert eine NVIDIA-GPU über `deploy.resources.reservations.devices`.

### Projekt übertragen und starten

1. Den vollständigen Ordner `dockercomposetest/` auf den Zielrechner kopieren. Wichtig sind mindestens `docker-compose.yml`, `Dockerfile`, beide Requirements-Dateien, `src/`, `tests/` und `data/`.
2. Optional im Projektordner eine Datei `.env` für die Zielhardware anlegen:

   ```dotenv
   OLLAMA_MODEL=qwen2.5:14b
   OLLAMA_NUM_CTX=4096
   OLLAMA_REQUEST_TIMEOUT=300
   CAPEX_BIND_ADDRESS=127.0.0.1
   OPEN_WEBUI_BIND_ADDRESS=127.0.0.1
   ```

   Mit 16 GB VRAM ist ein quantisiertes 14B-Modell oft praktikabel, die tatsächliche Belegung hängt aber von Quantisierung, Kontext und Treiber ab. `qwen2.5:14b` benötigt laut aktuellem Modellbestand ungefähr 9 GB auf Platte; für Gewichte, Kontext/KV-Cache und Runtime wird zusätzlicher VRAM benötigt. Mit `OLLAMA_NUM_CTX=4096` beginnen und `ollama ps`/GPU-Auslastung während einer Anfrage prüfen. Falls es zu langsam ist oder nicht vollständig auf die GPU passt, kleineres LLM wählen oder Kontext reduzieren. Das zusätzliche `qwen2.5-coder:7b` ist codeorientiert und nicht automatisch die bessere Wahl für Finanzfragen.

3. In PowerShell im Projektordner ausführen:

   ```powershell
   docker compose config --quiet
   docker compose up --build -d
   docker compose ps -a
   ```

4. Beim allerersten Start Modell-Download beobachten:

   ```powershell
   docker compose logs -f ollama-models
   ```

   Erst wenn `ollama-models` erfolgreich beendet wurde, startet `capex-app` aufgrund der Compose-Abhängigkeit. Das Einmal-Setup kann beim ersten Start länger dauern. Bei späteren Starts sind Modelle im persistenten Volume und müssen nicht erneut heruntergeladen werden.

5. Oberflächen öffnen:
   - CapEx-GUI: <http://localhost:8501>
   - Open WebUI: <http://localhost:3000>
   - FastAPI-Dokumentation: <http://localhost:8501/docs>

### Modell wechseln

In `.env` `OLLAMA_MODEL` ändern. Für den Wechsel auf ein Modell, das noch nicht im Volume liegt, das Modell herunterladen und die Dienste mit der neuen Konfiguration neu erzeugen:

```powershell
docker exec ollama_service ollama pull qwen2.5:14b
docker compose up -d --force-recreate ollama-models capex-app
```

`OLLAMA_MODEL` muss auch für Open WebUI nicht separat gesetzt werden: Open WebUI sieht die Modelle desselben Ollama-Servers und lässt das Chat-Modell in der Weboberfläche auswählen. Die Auswahl dort ändert nicht automatisch das in `.env` konfigurierte Modell der CapEx-App.

### Netzwerk und Sicherheit

Die Host-Ports sind standardmäßig an `127.0.0.1` gebunden. Damit sind die Oberflächen nur auf dem Docker-Host erreichbar. Für einen kontrollierten Intranetbetrieb bevorzugt einen HTTPS-Reverse-Proxy mit Authentifizierung verwenden. Die CapEx-App selbst hat in diesem Prototyp keine eigene Anmeldung. Sie nicht einfach ungeschützt auf `0.0.0.0` veröffentlichen. Ollamas Port 11434 bleibt bewusst unveröffentlicht und ist nur für andere Compose-Dienste erreichbar.

## 3. Die 15 wichtigsten Diagnose- und Wartungsbefehle

Alle Compose-Befehle unten im Verzeichnis `dockercomposetest/` ausführen. Die App- und Ollama-Logs gehen auf Standardausgabe und sind die erste Anlaufstelle bei Fehlern. Vertrauliche Inhalte oder Prompts nicht unbedacht in Logs kopieren oder weitergeben.

| Nr. | Befehl | Wofür / worauf achten |
|---:|---|---|
| 1 | `docker compose ps -a` | Status aller Dienste. `ollama-models` mit `Exited (0)` ist nach erfolgreichem Modell-Download normal; `capex-app`, `ollama`, `open-webui` sollten laufen. |
| 2 | `docker compose config --quiet` | Prüft YAML, Variablen und Compose-Konfiguration, ohne Container zu starten. |
| 3 | `docker compose logs -f --tail=100 capex-app` | App-Start, `/api/forecast`-Fehler, Tracebacks. Mit `Ctrl+C` nur die Logansicht beenden, nicht den Dienst. |
| 4 | `docker compose logs -f --tail=100 ollama` | Modell-Ladefehler, GPU-/Runner-Probleme und eingehende Modellanfragen. |
| 5 | `docker compose logs -f --tail=100 open-webui` | Anmeldung, WebUI-Fehler, Tool-/Modellabfragen und Verbindungsprobleme zu Ollama. |
| 6 | `docker exec ollama_service ollama list` | Heruntergeladene/verfügbare Modelle. Eine Modellzeile bedeutet nicht, dass es gerade im VRAM liegt. |
| 7 | `docker exec ollama_service ollama ps` | Aktuell geladene Modelle, Prozessor (GPU/CPU), Kontext und Entladezeit. Leere Ausgabe ist normal, wenn gerade keine Anfrage läuft. |
| 8 | `docker exec ollama_service ollama show qwen2.5:14b` | Modellinformationen und Fähigkeiten prüfen. Modellnamen bei Bedarf an `.env` anpassen. |
| 9 | `docker exec ollama_service ollama run qwen2.5:14b "Antworte nur mit: Modell erreichbar."` | Ollama direkt testen, unabhängig von GUI, API und RAG. Dauert die erste Antwort lange, beobachte parallel `ollama ps` und die Ollama-Logs. |
| 10 | `Invoke-RestMethod http://localhost:8501/api/health` | CapEx-API und Erreichbarkeit Ollamas prüfen. Erwartet: `status = ok`; `model_available` sollte `True` sein. |
| 11 | `(Invoke-WebRequest -UseBasicParsing http://localhost:3000).StatusCode` | Prüft, ob Open WebUI eine HTTP-Antwort liefert (üblicherweise `200`). |
| 12 | `docker compose exec capex-app pytest -q -k "homepage or multiple_files or too_many_files or malformed_history or pdf_content_is_indexed or csv_numeric_sum_is_exact_without_llm"` | Schnelle Tests ohne echte LLM-Arithmetik. Chroma verwendet hier ein Mock-Embedding; getestet werden GUI/API-Vertrag, Limits, CSV-Rechenschicht und Chroma-Speichern/Retrieval. |
| 13 | `docker compose exec capex-app pytest -q tests/test_capex.py::test_csv_llm_forecast_calculation` | Isolierter Modellqualitätstest: lässt Qwen selbst die CSV-Summe berechnen. Er kann absichtlich fehlschlagen, wenn das Modell nicht `328200` liefert. |
| 14 | `docker compose restart capex-app` | Startet nur API und GUI neu, ohne Image-Neubau. Auch nach Änderungen in `src/` nötig, weil Uvicorn nicht mit `--reload` läuft. |
| 15 | `docker compose up -d --force-recreate capex-app` | Erzeugt nur den App-Container neu, ohne Image-Build. Nach Änderungen an `.env`/Container-Umgebung verwenden; bei neuen Python-Paketen oder Dockerfile-Änderungen stattdessen `docker compose up --build -d capex-app`. |

Für die anderen Dienste gilt derselbe gezielte Neustart: `docker compose restart ollama` beziehungsweise `docker compose restart open-webui`. Ein Ollama-Neustart entlädt aktive Modelle aus dem Speicher; das `ollama_data`-Volume bleibt bestehen.

### Fehlerbilder schnell einordnen

| Beobachtung | Wahrscheinliche Ursache / nächster Schritt |
|---|---|
| GUI antwortet nicht auf Port 8501 | `docker compose ps -a`, danach `docker compose logs --tail=100 capex-app`; zusätzlich Bind-Adresse und Host-Port prüfen. |
| Open WebUI antwortet nicht auf Port 3000 | `docker compose ps -a` und Open-WebUI-Logs prüfen. Beim ersten Start Datenbank-/Modellinitialisierung abwarten. |
| `/api/health` meldet Ollama nicht erreichbar | Ollama-Containerstatus und `docker compose logs ollama` prüfen; `OLLAMA_HOST` in Compose muss intern `http://ollama:11434` sein. |
| `model_available` ist `False` | `.env`-Modellname mit `docker exec ollama_service ollama list` vergleichen; das konfigurierte Modell pullen und `capex-app` neu erzeugen. |
| `ollama ps` ist leer | Kein Modell wird gerade inferiert. Nach einer Anfrage erneut prüfen; `ollama list` zeigt die installierten Modelle. |
| PDF-Analyse liefert 502 | App-Logs enthalten den eigentlichen Traceback. Prüfen, ob `nomic-embed-text` installiert ist, PDF lesbar ist und die Inferenz erreichbar ist. |
| GPU wird nicht genutzt / Antwort sehr langsam | `ollama ps`-Spalte `PROCESSOR`, Host-Treiber, WSL2/Docker-GPU-Passthrough und Kontextlänge prüfen. |
| Test `test_csv_llm_forecast_calculation` schlägt fehl | Das ist ein Qualitätssignal: Das Modell hat die einfache Summe aus der Test-CSV falsch berechnet. Die deterministische numerische Teststrecke ist separat und soll trotzdem bestehen. |

### Wann ist ein Neubau erforderlich?

- **Kein Build nötig:** einzelner Container-Neustart, Logs ansehen, API-/Modellverfügbarkeit prüfen, Ollama-Modell direkt testen.
- **Kein Build nötig, aber Container neu erzeugen:** neue Umgebungsvariablen in `.env` aktivieren (`docker compose up -d --force-recreate capex-app`).
- **Build nötig:** `Dockerfile`, `requirements-base.txt` oder `requirements.txt` geändert (`docker compose up --build -d capex-app`).
- **Kein App-Build nötig:** ein Ollama-Modell neu herunterladen (`docker exec ollama_service ollama pull <modell>`). Danach muss die App-Konfiguration auf den Namen zeigen, wenn sie das Modell verwenden soll.

`docker compose down` stoppt und entfernt die Compose-Container und das Netzwerk, lässt Named Volumes aber bestehen. Ein anschließendes `docker compose up -d` startet die Container erneut. **`docker compose down -v` löscht dagegen persistente Volumes** und sollte nicht als allgemeiner Neustart verwendet werden.