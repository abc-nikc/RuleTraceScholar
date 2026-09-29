"""Research Replay Capsule APIs."""

from fastapi import APIRouter, HTTPException, Query

from app.store import get_capsule, list_capsules
from research_audit import compare_capsules


router = APIRouter(prefix="/api/audit", tags=["research-audit"])


@router.get("/sessions/{session_id}/capsules")
async def session_capsules(session_id: str):
    capsules = list_capsules(session_id)
    return {
        "session_id": session_id,
        "capsules": [
            {
                "capsule_id": item["capsule_id"],
                "created_at": item["created_at"],
                "query": item["query"],
                "answer_hash": item["answer_hash"],
                "capsule_hash": item["capsule_hash"],
                "decision": item.get("trace", {}).get("decision"),
                "reliability_score": item.get("trace", {}).get("reliability_score"),
            }
            for item in capsules
        ],
    }


@router.get("/capsules/{capsule_id}")
async def capsule_detail(capsule_id: str):
    capsule = get_capsule(capsule_id)
    if not capsule:
        raise HTTPException(status_code=404, detail="Replay capsule not found")
    return capsule


@router.get("/compare")
async def compare_replays(
    left: str = Query(..., description="First capsule id"),
    right: str = Query(..., description="Second capsule id"),
):
    left_capsule = get_capsule(left)
    right_capsule = get_capsule(right)
    if not left_capsule or not right_capsule:
        raise HTTPException(status_code=404, detail="One or both replay capsules were not found")
    return compare_capsules(left_capsule, right_capsule)
