import os
import shutil
import pandas as pd
import chromadb
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException

from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore

app = FastAPI(title="CapEx Forecast RAG API", version="1.0")

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
    
    reader = SimpleDirectoryReader(input_files=[pdf_path])
    documents = reader.load_data()
    
    chroma_client = chromadb.EphemeralClient()
    chroma_collection = chroma_client.create_collection("capex_pdf_runtime")
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

@app.post("/api/forecast")
async def api_forecast(
    file: UploadFile = File(...),
    query: str = Form(...)
):
    """Regelbetrieb-Endpunkt: Nimmt CSV oder PDF entgegen und führt den Forecast aus."""
    temp_dir = Path("/tmp/capex_uploads")
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / file.filename
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        if file.filename.endswith(".csv"):
            result = run_forecast_from_csv(str(file_path), query)
        elif file.filename.endswith(".pdf"):
            result = run_forecast_from_pdf_rag(str(file_path), query)
        else:
            raise HTTPException(status_code=400, detail="Nur .csv und .pdf Dateien werden unterstützt.")
            
        return {
            "filename": file.filename,
            "query": query,
            "forecast_result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8501)