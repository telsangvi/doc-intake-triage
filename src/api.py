"""FastAPI service + a one-page review queue UI.

Run it:
    uvicorn src.api:app --reload
    open http://127.0.0.1:8000

The point of this file is the deployment seam: the same pipeline the CLI
uses is exposed over HTTP, so a customer's system can call it and a human
can look at the output in a browser.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse

from .config import settings
from .llm import get_client
from .pipeline import process_file

app = FastAPI(title="Document Intake Triage", version="0.1.0")
APP_DIR = Path(__file__).resolve().parent.parent / "app"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": settings.provider}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(APP_DIR / "index.html")


@app.post("/extract")
async def extract(file: UploadFile = File(...)) -> dict:
    """Process a single uploaded document."""
    return (await _process_uploads([file]))[0]


@app.post("/queue")
async def queue(files: list[UploadFile] = File(...)) -> list[dict]:
    """Process a batch and return the review queue."""
    return await _process_uploads(files)


async def _process_uploads(files: list[UploadFile]) -> list[dict]:
    client = get_client()
    out: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        for upload in files:
            dest = Path(tmp) / Path(upload.filename or "upload.txt").name
            dest.write_bytes(await upload.read())
            result = process_file(dest, client)
            # Keep the original filename in the response, not the temp path.
            result.source_file = upload.filename or dest.name
            out.append(result.model_dump(mode="json"))
    return out
