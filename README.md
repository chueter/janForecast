# Local & Datenschutzkonforme Capex Forecast Architektur

Eine schlanke, browserbasierte RAG-Lösung (Retrieval-Augmented Generation) zur datenschutzkonformen Analyse historischer Investitionsdaten (Capex) und interaktiven Erstellung von Capex-Prognosen. Die Lösung läuft zu 100 % lokal ohne Cloud-Abhängigkeit oder externen Datenabfluss.

## Part 1: Status Quo & Funktionsumfang (Lokaler Prototyp)

### 1. Motivation & Problemstellung

Bei der Erstellung von Capex-Forecasts werden hochsensible Unternehmensdaten verarbeitet (z. B. historische Anlagenspiegel, strategische Erweiterungspläne, Budget-Obergrenzen). Bei der Nutzung kommerzieller Public-Cloud-APIs (z. B. OpenAI) ohne strikt vertraglich geregelte Data Boundaries besteht das Risiko des ungewollten Abflusses von Betriebsgeheimnissen.

Dieser Prototyp beweist, dass moderne Open-Source-LLMs (wie `Qwen 2.5` oder `Llama 3.1`) in Kombination mit einer lokalen Inferenz-Engine (Ollama) hervorragende Qualitäten bei der Verarbeitung und Analyse von Finanzdaten liefern – und das auf hauseigener Hardware.

### 2. Technische Architektur des Prototyps

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ BRWOSER (Lokale Web-Anwendung: index.html)                                  │
│                                                                             │
│  ┌──────────────────────┐  PDF.js   ┌────────────────────────────────────┐ │
│  │ Local PDF/TXT Reader ├──────────►│ Client-side Text Extraction        │ │
│  └──────────────────────┘           └─────────────────┬──────────────────┘ │
│                                                       │                    │
│  ┌──────────────────────┐           ┌─────────────────▼──────────────────┐ │
│  │ Interactive Chat UI  │◄─────────►│ Context & History Aggregator       │ │
│  └──────────────────────┘           └─────────────────┬──────────────────┘ │
│                                                       │                    │
│  ┌──────────────────────┐ html2pdf  ┌─────────────────▼──────────────────┐ │
│  │ PDF Report Export    │◄──────────│ HTML Report Renderer               │ │
│  └──────────────────────┘           └─────────────────┬──────────────────┘ │
└───────────────────────────────────────────────────────┼────────────────────┘
                                                        │ HTTP / REST API
                                                        │ (OpenAI-Format)
                                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ INFERENZ-SERVER (Lokal / GPU Host)                                          │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Ollama Engine (Port 11434)                                            │  │
│  │  - Exposes REST API (/v1/chat/completions)                            │  │
│  │  - Manages VRAM allocation & Quantized Weights                        │  │
│  └──────────────────────────────────┬────────────────────────────────────┘  │
│                                     │ CUDA Driver                           │
│  ┌──────────────────────────────────▼────────────────────────────────────┐  │
│  │ Host GPU (Nvidia RTX 2070 / 16GB RTX Server)                          │  │
│  │  - Model: qwen2.5-coder:7b / qwen2.5:14b                              │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘

```

### 3. Kernkomponenten des Prototyps

1. **Client-Side Text Extraction (`pdf.js`):**

   * Dokumente (PDF, TXT, CSV) werden direkt im Browser des Nutzers gelesen und in strukturierte Text-Strings umgewandelt.

   * Keine Server-Uploads für das Parsing notwendig.

2. **Ollama Inferenz-Backend:**

   * Handhabt die GPU-Hardwarebeschleunigung über CUDA.

   * Stellt eine OpenAI-kompatible REST-Schnittstelle (`http://localhost:11434/v1`) bereit.

   * Betreibt hochleistungsfähige, quantisierte Open-Source-Modelle (`qwen2.5-coder:7b`, `qwen2.5:14b`).

3. **Interaktiver Erfassungs-Chat & Prompt Engineering:**

   * Führt historische Dokumenteninhalte mit den aktuellen, manuellen Chat-Eingaben des Nutzers zusammen.

   * Verwendet strikt quantitative System-Prompts, um Halluzinationen zu unterdrücken.

4. **Client-Side PDF Generator (`html2pdf.js`):**

   * Auf Aufforderung generiert das Modell eine strukturierte HTML-Tabelle nebst Zusammenfassung.

   * Der Browser wandelt dieses Layout direkt in ein exportierbares PDF-Dokument um.

### 4. Kurzanleitung: Lokaler Start (Development Setup)

1. **Ollama vorbereiten:**

   ```
   # Modell herunterladen
   ollama pull qwen2.5-coder:7b
   
   # Umgebungsvariable für CORS-Freigabe setzen (Windows PowerShell)
   [System.Environment]::SetEnvironmentVariable('OLLAMA_ORIGINS', '*', 'User')
   
   ```

   *(Danach Ollama im System-Tray neu starten).*

2. **Webserver starten & App öffnen:**

   ```
   # Im Projektordner ausführen:
   python -m http.server 8000
   
   ```

   Öffne im Browser: `http://localhost:8000`

## Part 2: Leitfaden zur Überführung in die Firmen-IT-Infrastruktur

Um den Prototyp in eine produktive, enterprise-fähige Umgebung zu überführen, müssen Kernaspekte in den Bereichen **Hosting, Netzwerk, Sicherheit, Vektorsuche (RAG) und Governance** angepasst werden.

### 1. Backend & Server-Infrastruktur

Statt Ollama auf einer lokalen Workstation auszuführen, wird die Inferenz-Engine zentral auf einem dedizierten Linux-GPU-Server (z. B. Ubuntu Server mit 1x oder 2x NVIDIA RTX 4090 / A4000) gehostet.

* **Dienst-Setup (Systemd):**
  Ollama wird als robuster Hintergrunddienst unter Linux registriert.
  `/etc/systemd/system/ollama.service`:

  ```
  [Unit]
  Description=Ollama Service
  After=network-online.target
  
  [Service]
  ExecStart=/usr/local/bin/ollama serve
  User=ollama
  Group=ollama
  Restart=always
  RestartSec=3
  Environment="OLLAMA_HOST=0.0.0.0:11434"
  Environment="OLLAMA_ORIGINS=https://capex-assistant.company.internal"
  
  [Install]
  WantedBy=default.target
  
  ```

* **Modell-Upgrades für 16 GB+ VRAM:**
  Auf dem Firmen-Server kann von 7B-Parametern auf leistungsfähigere Varianten aufgerüstet werden:

  ```
  ollama pull qwen2.5:14b    # Hervorragender Kompromiss aus Speed und Logik
  ollama pull llama3.1:8b     # Sehr starkes Befolgen von Instruktionen
  
  ```

### 2. Netzwerkanbindung & IT-Security

In der Unternehmensumgebung darf die KI-Schnittstelle nicht ungeschützt im Netzwerk exponiert werden.

1. **Reverse Proxy & SSL/TLS-Verschlüsselung:**
   Ein NGINX oder Traefik Proxy schaltet sich vor Ollama, um HTTPS zu erzwingen und CORS auf zugelassene Unternehmens-Domains einzuschränken.

   ```
   server {
       listen 443 ssl;
       server_name capex-api.company.internal;
   
       ssl_certificate /etc/ssl/certs/company_cert.pem;
       ssl_certificate_key /etc/ssl/certs/company_key.pem;
   
       location / {
           proxy_pass http://127.0.0.1:11434;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   
   ```

2. **Authentifizierung & Access Control:**

   * Einbau eines API-Gateway-Tokens oder SSO-Schutzes (z. B. OAuth2/OIDC via Active Directory / Entra ID), damit nur autorisierte Mitarbeiter aus der Finanzabteilung Zugriff erhalten.

### 3. Erweiterung: Serverseitiges RAG & Vektordatenbank

Wenn das Volumen historischer Capex-Dokumente hunderte von Seiten oder Excel-Dateien umfasst, stößt das reine Mitschicken des gesamten Texts im Browser-Kontext an Grenzen.

* **Upgrade-Pfad:**
  Ersetzung der browserseitigen Text-Extraktion durch eine serverbasierte Vektordatenbank (z. B. **ChromaDB**, **Qdrant** oder **pgvector**).

* **Automatisches Dokumenten-Ingestion:**
  Ein Python-Hintergrunddienst liest Netzlaufwerke (`S:\Finanzen\Capex_Historie`) automatisch ein, zerlegt die Dokumente in Abschnitte (Chunking), generiert Einbettungen (via `nomic-embed-text`) und stellt der Web-Applikation eine semantische Suche zur Verfügung.

### 4. Integration in die HTML-Anwendung

In der bestehenden HTML-Anwendung müssen für den Produktivbetrieb lediglich minimale Konfigurations-Variablen angepasst werden:

```
// =====================================================================
// ENTERPRISE IT CONFIGURATION
// =====================================================================
// Vorher (Prototyp):
// const OLLAMA_BASE = "http://localhost:11434";
// const MODEL_NAME  = "qwen2.5-coder:7b";

// Nachher (Produktivumgebung):
const OLLAMA_BASE = "https://capex-api.company.internal";
const MODEL_NAME  = "qwen2.5:14b";
// =====================================================================

```

### 5. Zusammenfassung der Vorteile für die IT-Governance

* **Geschäftsgeheimnisgesetz (GeschGehG) & DSGVO:** Vollständige Konformität, da keine Daten die Infrastruktur des Unternehmens verlassen.

* **Wartungsarmut:** Keine komplexen Container-Orchestrierungen (wie Kubernetes) zwingend erforderlich – ein einfacher Linux-Server mit GPU und NGINX genügt.

* **Kosteneffizienz:** Keine variablen API-Kosten pro Token wie bei Azure/OpenAI.