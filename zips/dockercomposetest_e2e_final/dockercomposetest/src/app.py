import os
import pandas as pd
import chromadb
from pathlib import Path

from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import VectorStoreIndex, Document, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore

def get_llm():
    """Initialisiert das Ollama LLM mit dynamischem Kontextfenster & deterministischer Temp 0.0."""
    model_name = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", 8192))
    ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434")

    return Ollama(
        model=model_name, 
        base_url=ollama_host,
        request_timeout=90.0,
        additional_kwargs={
            "options": {
                "num_ctx": num_ctx,
                "temperature": 0.0  # Deterministischer Output bei gleichem Input
            }
        }
    )

def run_forecast_from_csv(csv_path: str, query: str) -> str:
    """Pfad A: Führt eine CapEx-Prognose direkt auf der CSV-Datei aus."""
    llm = get_llm()
    df = pd.read_csv(csv_path)
    csv_text = df.to_csv(index=False)
    
    prompt = f"Basierend auf folgenden CSV-Daten:\n{csv_text}\n{query}"
    response = llm.complete(prompt)
    return str(response).strip()

def run_forecast_from_pdf_rag(pdf_path: str, query: str) -> str:
    """Pfad B: Führt eine CapEx-Prognose über RAG / Ingest aus dem PDF aus."""
    llm = get_llm()
    ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    embed_model = OllamaEmbedding(model_name="nomic-embed-text", base_url=ollama_host)
    
    # Textauslesung aus dem PDF (vereinfacht für RAG Ingest Test)
    from fpdf import FPDF
    # Wir lesen den Text aus der Datei über PyPDF oder LlamaIndex SimpleDirectoryReader
    from llama_index.core import SimpleDirectoryReader
    reader = SimpleDirectoryReader(input_files=[pdf_path])
    documents = reader.load_data()
    
    chroma_client = chromadb.EphemeralClient()
    chroma_collection = chroma_client.create_collection("capex_pdf_test")
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    index = VectorStoreIndex.from_documents(
        documents, 
        storage_context=storage_context, 
        embed_model=embed_model
    )
    
    rag_engine = index.as_query_engine(llm=llm)
    response = rag_engine.query(query)
    return str(response).strip()

def main():
    print("==================================================")
    print(" Starte Erweiterten CapEx & RAG Test-Service")
    print("==================================================")

    ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    print(f"Verbinde mit Ollama unter: {ollama_host}")

    df = pd.DataFrame({
        "Projekt": ["Server-Upgrade", "CNC-Maschine", "Büromöbel", "Lager-Erweiterung"],
        "Kategorie": ["IT", "Produktion", "HVAC", "Produktion"],
        "Capex_2024": [50000, 120000, 15000, 200000],
        "Wachstum_Prozent": [5.0, 3.5, 0.0, 2.0]
    })
    df["Capex_2025"] = df["Capex_2024"] * (1 + df["Wachstum_Prozent"] / 100)
    
    print("Verfügbarer DataFrame:")
    print(df)
    print("==================================================")

if __name__ == "__main__":
    main()
