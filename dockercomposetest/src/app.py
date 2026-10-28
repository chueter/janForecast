import os
import time
import pandas as pd
import chromadb

from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import VectorStoreIndex, Document, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore

# Initialisiere dein lokales Qwen-Modell direkt über LlamaIndex
llm = Ollama(model="qwen2.5-coder:7b", request_timeout=60.0)

def main():
    print("==================================================")
    print(" Starte Erweiterten CapEx & RAG Test-Service")
    print("==================================================")

    
    ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    print(f"Verbinde mit Ollama unter: {ollama_host}")
    
    # LLM & Embedding-Modell initialisieren
    model_name = "qwen2.5-coder:7b"
    embed_model_name = "nomic-embed-text"
    
    llm = Ollama(model=model_name, base_url=ollama_host, request_timeout=90.0)
    embed_model = OllamaEmbedding(model_name=embed_model_name, base_url=ollama_host)
    
    # ---------------------------------------------------------
    # TEIL 1: Structured Data Analysis via PandasQueryEngine
    # ---------------------------------------------------------
    print("TEIL 1: PandasQueryEngine (Strukturierte CapEx-Analyse)")
    
    df = pd.DataFrame({
        "Projekt": ["Server-Upgrade", "CNC-Maschine", "Büromöbel", "Lager-Erweiterung"],
        "Kategorie": ["IT", "Produktion", "HVAC", "Produktion"],
        "Capex_2024": [50000, 120000, 15000, 200000],
        "Wachstum_Prozent": [5.0, 3.5, 0.0, 2.0]
    })
    df["Capex_2025"] = df["Capex_2024"] * (1 + df["Wachstum_Prozent"] / 100)
    
    print("Verfügbarer DataFrame:")
    print(df)
    
    try:
        query_engine = PandasQueryEngine(df=df, llm=llm, verbose=True)
        query_text = "Wie hoch ist der Gesamte CapEx für 2025 in der Kategorie Produktion?"
        print(f"Frage an PandasQueryEngine: '{query_text}'")
        
        response = query_engine.query(query_text)
        print("Antwort der PandasQueryEngine:")
        print(response)
    except Exception as e:
        print(f"Hinweis: Konnte PandasQueryEngine nicht ausführen. Ist '{model_name}' geladen? Details: {e}")
        print("Tipp: Führe aus: docker exec -it ollama_service ollama run qwen2.5-coder:7b")

    # ---------------------------------------------------------
    # TEIL 2: Unstructured Text Retrieval via ChromaDB RAG
    # ---------------------------------------------------------
    print("TEIL 2: ChromaDB + Ollama Embeddings (Freitext / Freigaben)")
    
    sample_docs = [
        Document(text="Freigabenote IT-Infrastruktur 2025: Das Server-Upgrade wurde aufgrund steigender Cloud-Kosten priorisiert."),
        Document(text="Produktionsstrategie: Die Anschaffung der CNC-Maschine dient der Kapazitätserweiterung im Werk Nord."),
        Document(text="Nachhaltigkeitsrichtlinie: HVAC-Investitionen (Büromöbel/Klima) sind für 2025 vorsorglich gedeckelt.")
    ]
    
    try:
        # In-Memory ChromaDB Client für einfachen Test im Container
        chroma_client = chromadb.EphemeralClient()
        chroma_collection = chroma_client.create_collection("capex_docs")
        
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        print("Erstelle Vektor-Index mit nomic-embed-text...")
        index = VectorStoreIndex.from_documents(
            sample_docs, 
            storage_context=storage_context, 
            embed_model=embed_model
        )
        
        rag_engine = index.as_query_engine(llm=llm)
        rag_query = "Warum wurde das Server-Upgrade in der IT priorisiert?"
        print(f"Frage an RAG: '{rag_query}'")
        
        rag_response = rag_engine.query(rag_query)
        print("Antwort des RAG-Systems:")
        print(rag_response)
        
    except Exception as e:
        print(f"Hinweis: Konnte RAG/ChromaDB Test nicht ausführen. Ist '{embed_model_name}' geladen? Details: {e}")
        print("Tipp: Führe aus: docker exec -it ollama_service ollama pull nomic-embed-text")

    print("==================================================")
    print(" Test-Durchlauf abgeschlossen.")
    print("==================================================")

if __name__ == "__main__":
    main()
