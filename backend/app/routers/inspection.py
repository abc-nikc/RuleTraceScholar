"""Read-only knowledge-base, retrieval, and conversation-memory inspection APIs."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.dependencies import get_checkpointer, get_retriever
from app.store import get_session, list_files
from config import Config
from app.runtime_settings import get_runtime_settings


router = APIRouter(prefix="/api/inspection", tags=["inspection"])


def _paper_record(paper_id: str) -> dict[str, Any]:
    for record in list_files():
        if record.get("paper_id") == paper_id:
            return record
    raise HTTPException(status_code=404, detail="Paper not found")


def _filter_for_paper(paper_id: str) -> str:
    return f"paper_id == {json.dumps(paper_id, ensure_ascii=False)}"


def _query_rows(store, paper_id: str, output_fields: list[str]) -> list[dict[str, Any]]:
    rows = store.client.query(
        collection_name=store.collection_name,
        filter=_filter_for_paper(paper_id),
        output_fields=output_fields,
        limit=16384,
    )
    return [dict(row) for row in rows]


def _count_rows(store, paper_id: str) -> int:
    rows = store.client.query(
        collection_name=store.collection_name,
        filter=_filter_for_paper(paper_id),
        output_fields=["count(*)"],
    )
    return int(rows[0].get("count(*)", 0)) if rows else 0


def _paper_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    retriever = get_retriever()
    children = _query_rows(
        retriever._child_store,
        record["paper_id"],
        ["node_type", "page_num", "section_type", "section_path"],
    )
    node_types = Counter(str(row.get("node_type") or "unknown") for row in children)
    section_types = Counter(str(row.get("section_type") or "other") for row in children)
    pages = sorted({int(row["page_num"]) for row in children if isinstance(row.get("page_num"), int)})
    return {
        **record,
        "index": {
            "children": len(children),
            "parents": _count_rows(retriever._parent_store, record["paper_id"]),
            "node_types": dict(node_types.most_common()),
            "section_types": dict(section_types.most_common()),
            "indexed_pages": pages,
        },
    }


@router.get("/papers")
async def inspect_papers():
    runtime = get_runtime_settings()
    pipeline = ["dense + BM25", "RRF"]
    if runtime.retrieval.rerank:
        pipeline.append("CrossEncoder")
    if runtime.retrieval.diversify:
        pipeline.append("diversity")
    if runtime.retrieval.expand_parent:
        pipeline.append("parent expansion")
    records = list_files()
    papers = await asyncio.gather(*[
        asyncio.to_thread(_paper_snapshot, record) for record in records
    ])
    retriever = get_retriever()
    cache = retriever.cache
    return {
        "papers": papers,
        "rag": {
            "collection": Config.COLLECTION_NAME,
            "embedding_model": Config.EMBEDDING_MODEL,
            "reranker_model": Config.RERANKER_MODEL,
            "retrieval": " -> ".join(pipeline),
            "top_k": runtime.retrieval.top_k,
            "fetch_k": runtime.retrieval.fetch_k,
            "rrf_k": runtime.retrieval.rrf_k,
            "rerank": runtime.retrieval.rerank,
            "expand_parent": runtime.retrieval.expand_parent,
            "diversify": runtime.retrieval.diversify,
            "diversity_weight": runtime.retrieval.diversity_weight,
            "chunking": runtime.chunking.model_dump(),
            "cache_enabled": cache is not None,
            "cache_entries": len(cache._store) if cache is not None else 0,
            "cache_similarity_threshold": cache.threshold if cache is not None else None,
        },
    }


@router.get("/papers/{paper_id}/chunks")
async def inspect_chunks(
    paper_id: str,
    level: Literal["children", "parents"] = Query("children"),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
):
    _paper_record(paper_id)
    retriever = get_retriever()
    store = retriever._child_store if level == "children" else retriever._parent_store
    fields = [
        "text", "paper_id", "chunk_id", "node_id", "node_type", "page_num",
        "order", "section_path", "section_type", "vlm_description",
    ]
    if level == "children":
        fields.append("chunk_parent_id")
    rows = await asyncio.to_thread(_query_rows, store, paper_id, fields)
    rows.sort(key=lambda row: (
        int(row.get("page_num") or 0),
        int(row.get("order") or 0),
        str(row.get("chunk_id") or ""),
    ))
    items = []
    for row in rows[offset:offset + limit]:
        items.append({
            "chunk_id": row.get("chunk_id"),
            "parent_id": row.get("chunk_parent_id"),
            "node_id": row.get("node_id"),
            "node_type": row.get("node_type"),
            "page": row.get("page_num"),
            "order": row.get("order"),
            "section": row.get("section_path"),
            "section_type": row.get("section_type"),
            "text": row.get("text", ""),
            "vlm_description": row.get("vlm_description", ""),
        })
    return {
        "paper_id": paper_id,
        "level": level,
        "total": len(rows),
        "offset": offset,
        "limit": limit,
        "items": items,
    }


@router.get("/sessions/{session_id}/memory")
async def inspect_memory(session_id: str):
    runtime = get_runtime_settings()
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    config = {"configurable": {"thread_id": session_id}}
    try:
        checkpoint = await get_checkpointer().aget(config)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Memory unavailable: {exc}") from exc
    values = (checkpoint or {}).get("channel_values") or {}
    messages = []
    for message in values.get("messages", []):
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        elif isinstance(message, SystemMessage):
            role = "system"
        else:
            role = message.__class__.__name__
        content = message.content if isinstance(message.content, str) else str(message.content)
        messages.append({
            "role": role,
            "content": content,
            "citation_count": len(getattr(message, "additional_kwargs", {}).get("citations", [])),
        })
    return {
        "session_id": session_id,
        "title": session.get("title"),
        "memory_policy": {
            "type": "sliding message window + LLM-compressed older context",
            "persistent_backend": "PostgreSQL LangGraph checkpoint",
            "window_size": runtime.memory.window_size,
            "summarization_enabled": runtime.memory.summarization_enabled,
            "note": "The summary is empty until the active message window is exceeded.",
        },
        "summary": values.get("summary", ""),
        "active_message_count": len(messages),
        "messages": messages,
        "working_state": {
            "last_query": values.get("query", ""),
            "query_type": values.get("query_type", ""),
            "paper_ids": values.get("paper_ids", []),
            "sub_queries": values.get("sub_queries", []),
            "citation_count": len(values.get("citations", [])),
        },
    }
