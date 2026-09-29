"""Runtime tuning controls for retrieval, chunking, and memory."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException

from config import Config
from app.dependencies import get_checkpointer, get_pdf_parser, get_rag_integration, get_retriever
from app.runtime_settings import (
    RuntimeSettings,
    get_runtime_settings,
    reset_runtime_settings,
    save_runtime_settings,
)
from app.store import add_file, get_file, get_session


router = APIRouter(prefix="/api/settings", tags=["settings"])
_reindex_lock = asyncio.Lock()


def _settings_response(settings: RuntimeSettings) -> dict:
    return {
        "settings": settings.model_dump(),
        "effects": {
            "retrieval": "Applies to the next question without restarting.",
            "chunking": "Applies to new uploads; existing papers must be reindexed.",
            "memory": "Applies to subsequent turns; existing checkpoint content is retained.",
        },
    }


def _clear_retrieval_cache() -> None:
    retriever = get_retriever()
    if retriever and retriever.cache:
        retriever.cache.clear()


@router.get("")
async def read_settings():
    return _settings_response(get_runtime_settings())


@router.put("")
async def update_settings(settings: RuntimeSettings):
    saved = save_runtime_settings(settings)
    _clear_retrieval_cache()
    return _settings_response(saved)


@router.delete("")
async def restore_default_settings():
    restored = reset_runtime_settings()
    _clear_retrieval_cache()
    return _settings_response(restored)


@router.post("/papers/{file_id}/reindex")
async def reindex_paper(file_id: str):
    """Rebuild one paper with the current chunking settings."""
    record = get_file(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    pdf_path = Path(Config.UPLOAD_DIR) / f"{file_id}.pdf"
    if not pdf_path.is_file():
        raise HTTPException(status_code=409, detail="Original PDF is not available for reindexing")

    if _reindex_lock.locked():
        raise HTTPException(status_code=409, detail="Another paper is currently being reindexed")

    async with _reindex_lock:
        try:
            nodes = await asyncio.to_thread(
                get_pdf_parser().parse, str(pdf_path), record["paper_id"]
            )
            integration = get_rag_integration()
            docs = integration.nodes_to_documents(nodes)
            parents, children = integration.create_chunks(docs)

            # Parsing completes before the old vectors are removed. The short
            # replacement window prevents duplicate chunks for the same paper.
            await asyncio.to_thread(
                get_retriever().get_updater().delete_paper, record["paper_id"]
            )
            stored = await asyncio.to_thread(
                integration.store_in_milvus, parents, children
            )
            if not stored:
                raise RuntimeError("Milvus rejected the rebuilt index")
            _clear_retrieval_cache()

            updated = add_file(
                file_id=record["file_id"],
                filename=record["filename"],
                paper_id=record["paper_id"],
                content_hash=record.get("content_hash", ""),
                size_bytes=record.get("size_bytes", 0),
                page_count=max((node.page_num for node in nodes), default=0),
                chunk_count=len(children),
            )
            return {
                "ok": True,
                "paper": updated,
                "parents": len(parents),
                "children": len(children),
                "chunking": get_runtime_settings().chunking.model_dump(),
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Reindex failed: {exc}") from exc


@router.delete("/memory/sessions/{session_id}")
async def reset_session_memory(session_id: str):
    if not get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    checkpointer = get_checkpointer()
    await checkpointer.adelete_thread(session_id)
    return {"ok": True, "session_id": session_id}
