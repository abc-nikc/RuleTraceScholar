"""File upload and management APIs."""

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from config import Config
from app.dependencies import get_retriever
from app.ingestion import ingest_pdf_content
from app.store import list_files, get_file, delete_file_record

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    results = []

    for f in files:
        try:
            filename = f.filename or "unnamed"
            results.append(await ingest_pdf_content(await f.read(), filename))
        except Exception as e:
            logger.exception(f"Failed to process {f.filename}")
            results.append({"filename": f.filename, "status": "error", "detail": str(e)})

    return {"files": results}


@router.get("")
async def get_files():
    return list_files()


@router.get("/{file_id}/content")
async def view_original_pdf(file_id: str):
    """Stream the exact uploaded PDF inline for inspection in the browser."""
    record = get_file(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(Config.UPLOAD_DIR) / f"{file_id}.pdf"
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Original PDF is no longer available")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=record["filename"],
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.delete("/{file_id}")
async def remove_file(file_id: str):
    record = delete_file_record(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    retriever = get_retriever()
    updater = retriever.get_updater()
    updater.delete_paper(record["paper_id"])

    save_path = Path(Config.UPLOAD_DIR) / f"{file_id}.pdf"
    save_path.unlink(missing_ok=True)

    figures_dir = Path("data/figures") / record["paper_id"]
    if figures_dir.exists():
        shutil.rmtree(figures_dir)

    return {"ok": True, "paper_id": record["paper_id"]}
