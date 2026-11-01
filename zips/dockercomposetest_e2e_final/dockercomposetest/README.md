# Docker Compose Test für CapEx Forecast (E2E CSV vs. PDF RAG Verification)

Dieses aktualisierte Paket enthält einen echten **End-to-End Test für den CapEx-Forecast**:
- **Pfad A (CSV Direct):** KI-Abfrage direkt auf strukturierten CSV-Daten.
- **Pfad B (PDF RAG):** KI-Abfrage via Ingestion aus der dynamisch aus der CSV erzeugten PDF.
- **Konsistenzprüfung:** Beide Pfade werden mit identischen Prompts und `temperature=0.0` ausgeführt und auf inhaltliche Identität (Zahlenwerte) geprüft.

## Anleitung zum Ausführen

1. **Stack bauen & starten:**
   ```bash
   docker compose up --build -d
   ```

2. **End-to-End Konsistenz-Tests ausführen:**
   ```bash
   docker exec -it capex_app pytest
   ```
