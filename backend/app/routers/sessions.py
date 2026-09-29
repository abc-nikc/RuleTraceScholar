"""Session management APIs."""

import logging

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from app.store import list_sessions, get_session, delete_session
from app.dependencies import get_checkpointer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
async def get_sessions():
    return list_sessions()


@router.get("/{session_id}")
async def get_session_detail(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/history")
async def get_history(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    config = {"configurable": {"thread_id": session_id}}
    checkpointer = get_checkpointer()
    try:
        checkpoint = await checkpointer.aget(config)
    except Exception:
        checkpoint = None

    if not checkpoint or not checkpoint.get("channel_values"):
        return {"session_id": session_id, "messages": []}

    messages = []
    last_sub_queries = checkpoint["channel_values"].get("sub_queries", [])
    for msg in checkpoint["channel_values"].get("messages", []):
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user", "content": msg.content})
        else:
            citations = msg.additional_kwargs.get("citations", [])
            explanation = msg.additional_kwargs.get("explanation")
            claim_tests = msg.additional_kwargs.get("claim_tests")
            repair = msg.additional_kwargs.get("repair")
            sub_queries = msg.additional_kwargs.get("sub_queries", [])
            capsule = msg.additional_kwargs.get("capsule")
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "citations": citations,
                "explanation": explanation,
                "claim_tests": claim_tests,
                "repair": repair,
                "sub_queries": sub_queries,
                "capsule": capsule,
            })

    # Older checkpoints predate per-message query-plan persistence. Expose the
    # final working-state plan on the last assistant turn so their RAG trace is
    # still inspectable after upgrading.
    if last_sub_queries:
        for item in reversed(messages):
            if item["role"] == "assistant" and not item.get("sub_queries"):
                item["sub_queries"] = last_sub_queries
                break

    return {"session_id": session_id, "messages": messages}


@router.delete("/{session_id}")
async def remove_session(session_id: str):
    ok = delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}
