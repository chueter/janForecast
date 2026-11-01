# Docker Compose Test für CapEx Forecast & Pytest Verification

Dieses aktualisierte Paket enthält das vollständige Setup inklusive **Pytest**, **PDF-Ingest Fixtures** und deterministischer LLM-Konfiguration (`temperature=0.0`, `num_ctx=8192`).

## Änderungen in diesem Build
1. **`requirements-base.txt` vs. `requirements.txt`**: Core-Pakete (Pandas, ChromaDB, LlamaIndex) in Base; `pytest` und `fpdf2` in standard requirements.
2. **`docker-compose.yml`**: `environment`-Variablen (`OLLAMA_MODEL`, `OLLAMA_NUM_CTX=8192`, `OLLAMA_HOST`) und Mount für `./tests` hinzugefügt.
3. **`src/app.py`**: Liest Umgebungsvariablen aus und erzwingt `temperature: 0.0` für deterministische Vergleiche.
4. **`tests/test_capex.py`**: Pytest-Suite mit `sample_csv_data` und `pdf_ingest` Fixture zur dynamischen PDF-Generierung aus CSV.

## Anleitung zum Ausführen

1. **Stack starten:**
   ```bash
   docker compose up --build -d
   ```

2. **Tests im Container ausführen:**
   ```bash
   docker exec -it capex_app pytest
   ```
