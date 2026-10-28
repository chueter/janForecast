# Docker Compose Test für CapEx Forecast, PandasQueryEngine & ChromaDB RAG

Dieses erweiterte Paket enthält die Konfiguration für deine RTX 2070 Max-Q (8GB VRAM) inkl. **PandasQueryEngine** und **ChromaDB Vector Store**.

## Anforderungsprüfung für deine Hardware (8 GB VRAM / 32 GB RAM)
- **Modelle:** 
  - LLM: `qwen2.5-coder:7b` (~4.5 GB VRAM)
  - Embedding: `nomic-embed-text` (~0.3 GB VRAM)
- **VRAM Total:** ~4.8 GB (passt perfekt in die 8 GB VRAM).
- **RAM Total:** ChromaDB + Pandas verbrauchen nur ca. 200–500 MB (deine 32 GB RAM sind mehr als ausreichend).

## Anleitung zum Testen

1. **Entpacken & Kopieren:**
   Kopiere den Inhalt dieses Archivs in dein Verzeichnis `/dockercomposetest/`.

2. **Zu GitHub pushen & ziehen:**
   ```bash
   git add dockercomposetest/
   git commit -m "Add LlamaIndex, PandasQueryEngine and ChromaDB"
   git push origin main
   ```

3. **Lokales Deployment starten:**
   ```bash
   cd /dockercomposetest/
   docker compose up --build -d
   ```

4. **Benötigte Modelle in Ollama ziehen:**
   ```bash
   # 1. Hauptmodell für Code & Analyse
   docker exec -it ollama_service ollama pull qwen2.5-coder:7b
   
   # 2. Embedding-Modell für RAG / Vektordatenbank
   docker exec -it ollama_service ollama pull nomic-embed-text
   ```

5. **Logs prüfen / Testlauf ansehen:**
   ```bash
   docker logs -f capex_app
   ```
