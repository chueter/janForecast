import json

import pytest
import pandas as pd
from pathlib import Path
from fpdf import FPDF
from fastapi.testclient import TestClient
import sys
sys.path.append("/app/src")

from app import (
    MAX_FILES,
    app,
    build_forecast_prompt,
    build_pdf_index,
    get_llm,
    run_forecast_from_csv,
)

@pytest.fixture
def sample_csv_data(tmp_path):
    """Erstellt temporäre CapEx-CSV-Daten für den Test."""
    csv_path = tmp_path / "capex_test.csv"
    df = pd.DataFrame({
        "Projekt": ["Server-Upgrade", "CNC-Maschine", "Büromöbel", "Lager-Erweiterung"],
        "Kategorie": ["IT", "Produktion", "HVAC", "Produktion"],
        "Capex_2024": [50000, 120000, 15000, 200000],
        "Wachstum_Prozent": [5.0, 3.5, 0.0, 2.0],
        "Capex_2025": [52500.0, 124200.0, 15000.0, 204000.0]
    })
    df.to_csv(csv_path, index=False)
    return csv_path

@pytest.fixture
def pdf_ingest(sample_csv_data, tmp_path):
    """Fixture, die aus der CSV dynamisch ein PDF mit Tabellendaten erzeugt."""
    pdf_path = tmp_path / "capex_test.pdf"
    df = pd.read_csv(sample_csv_data)
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    pdf.cell(200, 10, text="CapEx Forecast Uebersicht", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    for index, row in df.iterrows():
        line = f"Projekt: {row['Projekt']} | Kategorie: {row['Kategorie']} | 2024: {row['Capex_2024']} | 2025: {row['Capex_2025']}"
        pdf.cell(200, 10, text=line, new_x="LMARGIN", new_y="NEXT")
        
    pdf.output(str(pdf_path))
    return pdf_path

def test_homepage_serves_gui():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert '<title>CapEx Forecast</title>' in response.text
    assert 'type="file" accept=".csv,.pdf" multiple' in response.text
    assert "requestData.append('history'" in response.text
    assert 'id="chat-log"' in response.text

def test_forecast_accepts_multiple_files_and_history(monkeypatch):
    captured = {}

    def fake_forecast(file_paths, filenames, query, history):
        captured["filenames"] = filenames
        captured["query"] = query
        captured["history"] = history
        return "Mock-Antwort"

    monkeypatch.setattr("app.run_forecast_from_files", fake_forecast)
    with TestClient(app) as client:
        response = client.post(
            "/api/forecast",
            files=[
                ("files", ("plan.csv", b"project,amount\nA,10\n", "text/csv")),
                ("files", ("notes.pdf", b"%PDF-test", "application/pdf")),
            ],
            data={
                "query": "Und was ist mit den Risiken?",
                "history": json.dumps([{"role": "user", "content": "Fasse die Daten zusammen."}]),
            },
        )

    assert response.status_code == 200
    assert response.json()["filenames"] == ["plan.csv", "notes.pdf"]
    assert captured["query"] == "Und was ist mit den Risiken?"
    assert captured["history"] == [{"role": "user", "content": "Fasse die Daten zusammen."}]

def test_forecast_rejects_too_many_files():
    files = [
        ("files", (f"plan-{index}.csv", b"project,amount\nA,10\n", "text/csv"))
        for index in range(MAX_FILES + 1)
    ]
    with TestClient(app) as client:
        response = client.post(
            "/api/forecast",
            files=files,
            data={"query": "Summiere die Daten", "history": "[]"},
        )

    assert response.status_code == 400

def test_forecast_rejects_malformed_history():
    with TestClient(app) as client:
        response = client.post(
            "/api/forecast",
            files=[("files", ("plan.csv", b"project,amount\nA,10\n", "text/csv"))],
            data={
                "query": "Summiere die Daten",
                "history": json.dumps([{"role": [], "content": "Ungültig"}]),
            },
        )

    assert response.status_code == 400

def test_forecast_files_exist(sample_csv_data, pdf_ingest):
    """Prüft die Generierung der CSV- und PDF-Testdateien."""
    assert sample_csv_data.exists()
    assert pdf_ingest.exists()
    assert pdf_ingest.stat().st_size > 0

def test_pdf_content_is_indexed_and_retrievable_in_chroma(pdf_ingest):
    import chromadb
    from llama_index.core.embeddings import MockEmbedding

    index, collection, client = build_pdf_index(
        [str(pdf_ingest)],
        MockEmbedding(embed_dim=8),
    )
    second_index, second_collection, second_client = build_pdf_index(
        [str(pdf_ingest)],
        MockEmbedding(embed_dim=8),
    )
    try:
        assert collection.name != second_collection.name
        stored = collection.get(include=["documents", "metadatas"])
        stored_text = "\n".join(stored["documents"] or [])
        retrieved = index.as_retriever(similarity_top_k=2).retrieve(
            "Lager-Erweiterung CapEx 2025"
        )

        assert collection.count() > 0
        assert stored["ids"]
        assert len(stored["ids"]) == len(set(stored["ids"]))
        assert "Server-Upgrade" in stored_text
        assert "Lager-Erweiterung" in stored_text
        assert any(
            "Lager-Erweiterung" in result.node.get_content()
            for result in retrieved
        )
    finally:
        client.delete_collection(collection.name)
        second_client.delete_collection(second_collection.name)

def test_csv_numeric_sum_is_exact_without_llm(sample_csv_data, monkeypatch):
    query = "Wie hoch ist der Gesamte CapEx für 2025 in der Kategorie Produktion? Antwort nur als Gesamtsumme."

    monkeypatch.setattr("app.get_llm", lambda: pytest.fail("LLM should not calculate CSV sums"))
    response = run_forecast_from_csv(str(sample_csv_data), query)
    assert response == "328200"

def test_csv_llm_forecast_calculation(sample_csv_data):
    """Misst, ob das konfigurierte LLM die CSV-Summe selbst korrekt berechnet."""
    query = "Wie hoch ist der Gesamte CapEx für 2025 in der Kategorie Produktion? Antwort nur als Gesamtsumme."
    dataframe = pd.read_csv(sample_csv_data)
    csv_context = f"Datei: {sample_csv_data.name}\n{dataframe.to_csv(index=False)}"
    prompt = build_forecast_prompt(query, [], csv_context)
    response = str(get_llm().complete(prompt)).strip()

    assert "328200" in response or "328.200" in response, f"Unerwartete LLM-Antwort: {response}"

def test_end_to_end_csv_vs_pdf_forecast_consistency(sample_csv_data, pdf_ingest):
    """
    End-to-End Vergleichtest[cite: 20]:
    Vergleicht den Output von Pfad A (CSV) und Pfad B (PDF RAG Ingest) auf inhaltliche Konsistenz.
    """
    query = "Wie hoch ist der Gesamte CapEx für 2025 in der Kategorie Produktion?"
    
    # Pfad A: CSV Direct
    res_csv = run_forecast_from_csv(str(sample_csv_data), query)
    
    # Pfad B: PDF RAG Ingest
    from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext
    import chromadb
    from llama_index.vector_stores.chroma import ChromaVectorStore
    from llama_index.embeddings.ollama import OllamaEmbedding
    import os
    
    llm = get_llm()
    ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    embed_model = OllamaEmbedding(model_name="nomic-embed-text", base_url=ollama_host)
    
    reader = SimpleDirectoryReader(input_files=[str(pdf_ingest)])
    docs = reader.load_data()
    
    chroma_client = chromadb.EphemeralClient()
    chroma_collection = chroma_client.create_collection("pdf_e2e_test")
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    index = VectorStoreIndex.from_documents(docs, storage_context=storage_context, embed_model=embed_model)
    rag_engine = index.as_query_engine(llm=llm)
    res_pdf = str(rag_engine.query(query)).strip()
    
    assert "328200" in res_csv or "328.200" in res_csv, f"CSV Output fehlerhaft: {res_csv}"
    assert "328200" in res_pdf or "328.200" in res_pdf, f"PDF Output fehlerhaft: {res_pdf}"