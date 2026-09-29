"""Academic discovery and trusted arXiv import APIs."""

from __future__ import annotations

import logging
import re
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.ingestion import ingest_pdf_content
from config import Config
from app.store import get_file
from research_sources import (
    discover_papers,
    download_arxiv_pdf,
    extract_paper_context,
    explain_relatedness,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/discovery", tags=["academic-discovery"])


class ArxivImportRequest(BaseModel):
    arxiv_id: str = Field(min_length=4, max_length=40)
    title: str = Field(default="", max_length=300)


@router.get("/search")
async def search_papers(
    query: str = Query(..., min_length=2, max_length=300),
    limit: int = Query(10, ge=1, le=20),
):
    result = await discover_papers(query.strip(), limit)
    if not result["papers"] and not any(item["ok"] for item in result["providers"]):
        raise HTTPException(status_code=502, detail={"message": "All discovery providers failed", **result})
    return result


@router.get("/from-paper/{file_id}")
async def discover_from_uploaded_paper(
    file_id: str,
    limit: int = Query(12, ge=1, le=20),
):
    """Extract local references and discover related work from one upload."""
    record = get_file(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="Uploaded paper not found")
    path = Path(Config.UPLOAD_DIR) / f"{file_id}.pdf"
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Original PDF is no longer available")

    context = await asyncio.to_thread(
        extract_paper_context, path, Path(record["filename"]).stem
    )
    try:
        discovery = await discover_papers(context["related_query"], limit)
    except Exception as exc:
        logger.warning("Related-paper discovery failed for %s: %s", file_id, exc)
        discovery = {
            "papers": [],
            "providers": [{"provider": "multi-source", "ok": False, "detail": str(exc)}],
        }

    return {
        "source_paper": {
            "file_id": record["file_id"],
            "paper_id": record["paper_id"],
            "filename": record["filename"],
            "title": context["title"],
            "abstract": context["abstract"],
            "page_count": context["page_count"],
            "keywords": context["keywords"],
        },
        "references": context["references"],
        "reference_count": len(context["references"]),
        "related_query": context["related_query"],
        "related_papers": explain_relatedness(context, discovery.get("papers", []))[:limit],
        "providers": discovery.get("providers", []),
    }


@router.post("/import/arxiv")
async def import_arxiv(req: ArxivImportRequest):
    try:
        content = await download_arxiv_pdf(req.arxiv_id)
        title = re.sub(r"[^\w\-. ]+", "", req.title, flags=re.UNICODE).strip()
        filename = f"{title[:120]}_{req.arxiv_id}.pdf" if title else f"arxiv_{req.arxiv_id}.pdf"
        return await ingest_pdf_content(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to import arXiv paper %s", req.arxiv_id)
        raise HTTPException(status_code=502, detail=f"arXiv import failed: {exc}") from exc
