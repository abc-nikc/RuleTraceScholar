"""Shared PDF ingestion used by uploads and trusted online discovery."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from pathlib import Path

import aiofiles

from config import Config
from app.dependencies import get_pdf_parser, get_rag_integration, get_retriever
from app.store import add_file, get_file_by_hash


logger = logging.getLogger(__name__)


def safe_paper_id(filename: str) -> str:
    """Create a Milvus-filter-safe, stable identifier from a filename."""
    stem = Path(filename).stem.strip()
    cleaned = re.sub(r"[^\w\-.]+", "_", stem, flags=re.UNICODE).strip("_.")
    return (cleaned or f"paper_{uuid.uuid4().hex[:8]}")[:180]


async def ingest_pdf_content(content: bytes, filename: str) -> dict:
    """Parse, index, and persist one PDF without reporting false success."""
    if not filename.lower().endswith(".pdf"):
        return {"filename": filename, "status": "error", "detail": "Only PDF files are supported"}

    max_bytes = Config.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        return {
            "filename": filename,
            "status": "error",
            "detail": f"File exceeds {Config.MAX_UPLOAD_SIZE_MB}MB limit",
        }
    if not content.startswith(b"%PDF-"):
        return {"filename": filename, "status": "error", "detail": "Downloaded content is not a PDF"}

    content_hash = hashlib.sha256(content).hexdigest()
    existing = get_file_by_hash(content_hash)
    if existing:
        return {
            "filename": filename,
            "status": "duplicate",
            "detail": f"Same content as '{existing['filename']}'",
            "paper_id": existing["paper_id"],
            "file_id": existing["file_id"],
        }

    upload_dir = Path(Config.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    paper_id = safe_paper_id(filename)
    save_path = upload_dir / f"{file_id}.pdf"

    async with aiofiles.open(save_path, "wb") as out:
        await out.write(content)

    try:
        nodes = get_pdf_parser().parse(str(save_path), paper_id)
        integration = get_rag_integration()
        docs = integration.nodes_to_documents(nodes)
        parents, children = integration.create_chunks(docs)
        if not integration.store_in_milvus(parents, children):
            get_retriever().get_updater().delete_paper(paper_id)
            raise RuntimeError("The PDF was parsed, but Milvus indexing failed")

        record = add_file(
            file_id=file_id,
            filename=filename,
            paper_id=paper_id,
            content_hash=content_hash,
            size_bytes=len(content),
            page_count=max((node.page_num for node in nodes), default=0),
            chunk_count=len(children),
        )
        return {"filename": filename, "status": "ok", **record}
    except Exception:
        logger.exception("Failed to ingest %s", filename)
        save_path.unlink(missing_ok=True)
        try:
            get_retriever().get_updater().delete_paper(paper_id)
        except Exception:
            logger.warning("Could not clean partial vectors for %s", paper_id, exc_info=True)
        raise
