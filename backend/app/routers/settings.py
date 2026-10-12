"""Runtime tuning controls for retrieval, chunking, and memory."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter, HTTPException
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from config import Config
from app.dependencies import (
    clear_llm_cache,
    get_checkpointer,
    get_pdf_parser,
    get_rag_integration,
    get_retriever,
)
from app.runtime_settings import (
    LLMSettings,
    RuntimeSettings,
    clear_llm_api_key,
    get_llm_api_key,
    get_runtime_settings,
    llm_api_key_configured,
    reset_runtime_settings,
    save_llm_api_key,
    save_runtime_settings,
)
from app.store import add_file, get_file, get_session


router = APIRouter(prefix="/api/settings", tags=["settings"])
_reindex_lock = asyncio.Lock()


class SettingsUpdate(RuntimeSettings):
    api_key: str | None = Field(default=None, max_length=4096)
    clear_api_key: bool = False


class ModelConnectionRequest(BaseModel):
    llm: LLMSettings
    api_key: str | None = Field(default=None, max_length=4096)


def _ollama_api_root(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")


def _settings_response(settings: RuntimeSettings) -> dict:
    return {
        "settings": settings.model_dump(),
        "model_status": {
            "provider": settings.llm.provider,
            "model": settings.llm.model,
            "fast_model": settings.llm.fast_model or settings.llm.model,
            "base_url": settings.llm.base_url,
            "api_key_configured": llm_api_key_configured(settings),
        },
        "effects": {
            "retrieval": "Applies to the next question without restarting.",
            "chunking": "Applies to new uploads; existing papers must be reindexed.",
            "memory": "Applies to subsequent turns; existing checkpoint content is retained.",
            "llm": "Provider and model changes apply to the next question without restarting.",
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
async def update_settings(update: SettingsUpdate):
    if update.clear_api_key:
        clear_llm_api_key()
    elif update.api_key:
        save_llm_api_key(update.api_key)
    saved = save_runtime_settings(RuntimeSettings.model_validate(
        update.model_dump(exclude={"api_key", "clear_api_key"})
    ))
    clear_llm_cache()
    _clear_retrieval_cache()
    return _settings_response(saved)


@router.delete("")
async def restore_default_settings():
    restored = reset_runtime_settings()
    clear_llm_cache()
    _clear_retrieval_cache()
    return _settings_response(restored)


@router.get("/models/local")
async def list_local_models():
    settings = get_runtime_settings()
    base_url = (
        settings.llm.base_url
        if settings.llm.provider == "ollama"
        else Config.OLLAMA_BASE_URL
    )
    root = _ollama_api_root(base_url)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            tags_response, running_response = await asyncio.gather(
                client.get(f"{root}/api/tags"),
                client.get(f"{root}/api/ps"),
            )
            tags_response.raise_for_status()
            running_response.raise_for_status()
        running = {
            item.get("name") or item.get("model"): item
            for item in running_response.json().get("models", [])
        }
        models = []
        for item in tags_response.json().get("models", []):
            name = item.get("name") or item.get("model")
            if not name:
                continue
            active = running.get(name, {})
            total_size = int(active.get("size") or item.get("size") or 0)
            vram_size = int(active.get("size_vram") or 0)
            if not active:
                processor = "not_loaded"
            elif vram_size <= 0:
                processor = "cpu"
            elif total_size and vram_size >= total_size * 0.9:
                processor = "gpu"
            else:
                processor = "mixed"
            models.append({
                "name": name,
                "size": item.get("size", 0),
                "parameter_size": (item.get("details") or {}).get("parameter_size", ""),
                "quantization": (item.get("details") or {}).get("quantization_level", ""),
                "loaded": bool(active),
                "processor": processor,
                "size_vram": vram_size,
                "context_length": active.get("context_length"),
            })
        return {"ok": True, "endpoint": root, "models": models}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"无法连接本地 Ollama（{root}）：{exc}",
        ) from exc


@router.post("/models/test")
async def test_model_connection(request: ModelConnectionRequest):
    started = time.perf_counter()
    if request.llm.provider == "ollama":
        root = _ollama_api_root(request.llm.base_url)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{root}/api/show", json={"model": request.llm.model}
                )
                response.raise_for_status()
            manifest = response.json()
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama 模型校验失败：{exc}",
            ) from exc
        details = manifest.get("details") or {}
        return {
            "ok": True,
            "model": request.llm.model,
            "provider": request.llm.provider,
            "latency_seconds": round(time.perf_counter() - started, 2),
            "response_preview": " / ".join(
                item for item in (
                    details.get("family", ""),
                    details.get("parameter_size", ""),
                    details.get("quantization_level", ""),
                ) if item
            ),
        }

    key_settings = get_runtime_settings().model_copy(update={"llm": request.llm})
    api_key = request.api_key or get_llm_api_key(key_settings)
    if not api_key:
        raise HTTPException(status_code=400, detail="请填写 API Key，或先保存已配置的密钥。")

    options = dict(
        base_url=request.llm.base_url,
        model=request.llm.model,
        api_key=api_key,
        temperature=0,
        max_tokens=16,
        timeout=60,
        max_retries=0,
    )
    if request.llm.reasoning_supported:
        options["reasoning_effort"] = "none"
    try:
        response = await ChatOpenAI(**options).ainvoke("Reply with OK only.")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"模型连接测试失败：{exc}") from exc
    return {
        "ok": True,
        "model": request.llm.model,
        "provider": request.llm.provider,
        "latency_seconds": round(time.perf_counter() - started, 2),
        "response_preview": str(response.content)[:100],
    }


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
