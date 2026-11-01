import asyncio
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

import chromadb
import pandas as pd
import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore

app = FastAPI(title="CapEx Forecast Assistant", version="1.0")
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_TOTAL_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_FILES = 10
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARS = 12_000
FORECAST_SEMAPHORE = asyncio.Semaphore(1)


def get_llm():
    model_name = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", 4096))
    ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434")

    return Ollama(
        model=model_name,
        base_url=ollama_host,
        request_timeout=float(os.getenv("OLLAMA_REQUEST_TIMEOUT", "300")),
        additional_kwargs={
            "options": {
                "num_ctx": num_ctx,
                "temperature": 0.0,
            }
        },
    )


def run_forecast_from_csv(csv_path: str, query: str) -> str:
    return run_forecast_from_files(
        [Path(csv_path)], [Path(csv_path).name], query, []
    )


def run_forecast_from_pdf_rag(pdf_path: str, query: str) -> str:
    return run_forecast_from_files([Path(pdf_path)], [Path(pdf_path).name], query, [])


def build_forecast_prompt(
    query: str,
    history: list[dict[str, str]],
    csv_context: str,
) -> str:
    history_text = "\n".join(
        f"{message['role'].capitalize()}: {message['content']}"
        for message in history
    )
    sections = [
        "Du bist ein sorgfältiger Finanz- und CapEx-Analyst. Antworte auf Deutsch. "
        "Nutze nur belegbare Informationen aus den Quelldateien und dem Gespräch. "
        "Wenn Daten fehlen, weise darauf hin und erfinde keine Zahlen.",
    ]
    if csv_context:
        sections.append(f"CSV-Quelldaten:\n{csv_context}")
    if history_text:
        sections.append(f"Bisheriger Gesprächsverlauf:\n{history_text}")
    sections.append(f"Aktuelle Frage:\n{query}")
    return "\n\n".join(sections)


def calculate_csv_sum(query: str, dataframes: list[pd.DataFrame]) -> str | None:
    normalized_query = query.casefold()
    if not re.search(r"\b(?:gesamt\w*|summe|summier\w*|addier\w*|total|sum)\b", normalized_query):
        return None

    year_match = re.search(r"\b(20\d{2})\b", normalized_query)
    if year_match is None:
        return None
    year = year_match.group(1)

    total = 0.0
    for dataframe in dataframes:
        numeric_columns = set(dataframe.select_dtypes(include="number").columns)
        year_columns = [
            column
            for column in numeric_columns
            if year in str(column)
        ]
        capex_columns = [
            column
            for column in year_columns
            if "capex" in str(column).casefold()
        ]
        if len(capex_columns) == 1:
            value_column = capex_columns[0]
        elif len(year_columns) == 1:
            value_column = year_columns[0]
        else:
            return None

        category_matches = []
        for column in dataframe.columns:
            if column in numeric_columns:
                continue
            for value in dataframe[column].dropna().unique():
                category = str(value).strip()
                if category and re.search(
                    rf"(?<!\w){re.escape(category)}(?!\w)", query, re.IGNORECASE
                ):
                    category_matches.append((column, category))

        unique_matches = {
            (column, category.casefold())
            for column, category in category_matches
        }
        if len(unique_matches) != 1:
            return None

        category_column, category_value = next(iter(unique_matches))
        mask = (
            dataframe[category_column]
            .astype(str)
            .str.strip()
            .str.casefold()
            == category_value
        )
        if not mask.any():
            return None
        total += pd.to_numeric(dataframe.loc[mask, value_column], errors="coerce").sum()

    return str(int(total)) if total.is_integer() else f"{total:g}"


def build_pdf_index(pdf_paths: list[str], embed_model):
    documents = SimpleDirectoryReader(input_files=pdf_paths).load_data()
    chroma_client = chromadb.EphemeralClient()
    chroma_collection = chroma_client.create_collection(f"capex_pdf_{uuid4().hex}")
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        embed_model=embed_model,
    )
    return index, chroma_collection, chroma_client


def run_forecast_from_files(
    file_paths: list[Path],
    filenames: list[str],
    query: str,
    history: list[dict[str, str]],
) -> str:
    csv_sections = []
    csv_dataframes = []
    pdf_paths = []
    for file_path, filename in zip(file_paths, filenames):
        if file_path.suffix.lower() == ".csv":
            dataframe = pd.read_csv(file_path)
            csv_dataframes.append(dataframe)
            csv_sections.append(
                f"Datei: {filename}\n{dataframe.to_csv(index=False)}"
            )
        else:
            pdf_paths.append(str(file_path))

    if csv_dataframes and not pdf_paths:
        exact_sum = calculate_csv_sum(query, csv_dataframes)
        if exact_sum is not None:
            return exact_sum

    prompt = build_forecast_prompt(query, history, "\n\n".join(csv_sections))
    llm = get_llm()
    if not pdf_paths:
        return str(llm.complete(prompt)).strip()

    ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    embed_model = OllamaEmbedding(
        model_name="nomic-embed-text",
        base_url=ollama_host,
    )
    index, chroma_collection, chroma_client = build_pdf_index(pdf_paths, embed_model)
    try:
        response = index.as_query_engine(llm=llm).query(prompt)
        return str(response).strip()
    finally:
        chroma_client.delete_collection(chroma_collection.name)


def parse_history(history_json: str) -> list[dict[str, str]]:
    try:
        history = json.loads(history_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Der Chatverlauf ist ungültig.") from exc

    if not isinstance(history, list) or len(history) > MAX_HISTORY_MESSAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Der Chatverlauf darf höchstens {MAX_HISTORY_MESSAGES} Nachrichten enthalten.",
        )

    clean_history = []
    total_chars = 0
    for message in history:
        if not isinstance(message, dict):
            raise HTTPException(status_code=400, detail="Der Chatverlauf ist ungültig.")
        role = message.get("role")
        content = message.get("content")
        if (
            not isinstance(role, str)
            or role not in {"user", "assistant"}
            or not isinstance(content, str)
        ):
            raise HTTPException(status_code=400, detail="Der Chatverlauf ist ungültig.")
        total_chars += len(content)
        if total_chars > MAX_HISTORY_CHARS:
            raise HTTPException(
                status_code=400,
                detail="Der Chatverlauf ist zu umfangreich. Bitte starte einen neuen Chat.",
            )
        clean_history.append({"role": role, "content": content})
    return clean_history


@app.get("/", include_in_schema=False)
async def homepage():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def api_health():
    ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434").rstrip("/")
    model_name = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

    try:
        response = requests.get(f"{ollama_host}/api/tags", timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=503,
            detail="Ollama ist nicht erreichbar. Bitte den Dienststatus prüfen.",
        ) from exc

    model_available = any(
        model.get("name") == model_name
        or model.get("name", "").startswith(f"{model_name}:")
        for model in models
    )
    return {
        "status": "ok",
        "model": model_name,
        "model_available": model_available,
    }


@app.post("/api/forecast")
async def api_forecast(
    files: list[UploadFile] = File(...),
    query: str = Form(...),
    history: str = Form("[]"),
):
    if not files:
        raise HTTPException(status_code=400, detail="Bitte mindestens eine Datei auswählen.")
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Es sind höchstens {MAX_FILES} Dateien pro Anfrage erlaubt.",
        )
    if not query.strip():
        raise HTTPException(status_code=400, detail="Bitte eine Frage eingeben.")
    if len(query) > 20_000:
        raise HTTPException(status_code=400, detail="Die Frage ist zu lang.")
    clean_history = parse_history(history)

    uploads = []
    total_size = 0
    for file in files:
        filename = Path(file.filename or "").name
        extension = Path(filename).suffix.lower()
        if extension not in {".csv", ".pdf"}:
            raise HTTPException(
                status_code=400,
                detail=f"{filename or 'Datei'}: Nur CSV- und PDF-Dateien werden unterstützt.",
            )
        contents = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(contents) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"{filename} überschreitet das Limit von 20 MB.",
            )
        if not contents:
            raise HTTPException(status_code=400, detail=f"{filename} ist leer.")
        total_size += len(contents)
        if total_size > MAX_TOTAL_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Die Gesamtgröße aller Dateien darf 50 MB nicht überschreiten.",
            )
        uploads.append((filename, extension, contents))

    try:
        with tempfile.TemporaryDirectory(prefix="capex_upload_") as temp_dir:
            file_paths = []
            filenames = []
            for index, (filename, extension, contents) in enumerate(uploads):
                file_path = Path(temp_dir) / f"{index}{extension}"
                file_path.write_bytes(contents)
                file_paths.append(file_path)
                filenames.append(filename)
            async with FORECAST_SEMAPHORE:
                result = await run_in_threadpool(
                    run_forecast_from_files,
                    file_paths,
                    filenames,
                    query,
                    clean_history,
                )
    except Exception as exc:
        logger.exception("Forecast failed for uploaded files %s", [item[0] for item in uploads])
        raise HTTPException(
            status_code=502,
            detail="Die Analyse ist fehlgeschlagen. Bitte Dateien, CSV-Format und Ollama prüfen.",
        ) from exc

    return {
        "filenames": filenames,
        "query": query,
        "forecast_result": result,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8501)