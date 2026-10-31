import pytest
import pandas as pd
from pathlib import Path
from fpdf import FPDF
import sys
sys.path.append("/app/src")

from app import get_llm, run_forecast_from_csv

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

def test_forecast_files_exist(sample_csv_data, pdf_ingest):
    """Prüft die Generierung der CSV- und PDF-Testdateien."""
    assert sample_csv_data.exists()
    assert pdf_ingest.exists()
    assert pdf_ingest.stat().st_size > 0

def test_csv_forecast_calculation(sample_csv_data):
    """Prüft den deterministischen LLM-Forecast für Pfad A (CSV)[cite: 13, 20]."""
    query = "Wie hoch ist der Gesamte CapEx für 2025 in der Kategorie Produktion? Antwort nur als Gesamtsumme."
    response = run_forecast_from_csv(str(sample_csv_data), query)
    assert "328200" in response or "328.200" in response, f"Unerwartete Antwort: {response}"

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