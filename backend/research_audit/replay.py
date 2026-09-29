"""Build and compare portable Research Replay Capsules."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_capsule(
    *,
    session_id: str,
    query: str,
    answer: str,
    citations: list[dict[str, Any]],
    explanation: dict[str, Any],
    claim_tests: dict[str, Any],
    query_type: str,
    sub_query_count: int,
    runtime: dict[str, Any],
    repair: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a secret-free snapshot sufficient for auditing an answer."""
    evidence = [
        {
            "paper_id": item.get("paper_id", ""),
            "section": item.get("section", ""),
            "page": item.get("page", ""),
            "chunk_id": item.get("chunk_id", ""),
            "retrieval_rank": item.get("retrieval_rank"),
            "retrieval_relevance": item.get("retrieval_relevance"),
            "evidence_excerpt": item.get("evidence_excerpt", ""),
        }
        for item in citations
    ]
    created_at = time.time()
    capsule = {
        "schema_version": "1.0",
        "capsule_id": str(uuid.uuid4()),
        "session_id": session_id,
        "created_at": created_at,
        "query": query,
        "query_type": query_type,
        "sub_query_count": sub_query_count,
        "answer": answer,
        "answer_hash": _digest(answer),
        "evidence_hash": _digest(evidence),
        "evidence": evidence,
        "trace": {
            "decision": explanation.get("decision"),
            "reliability_score": explanation.get("reliability_score"),
            "metrics": explanation.get("metrics", {}),
            "rule_trace": explanation.get("rule_trace", []),
        },
        "claim_tests": claim_tests,
        "repair": repair or {"attempted": False, "applied": False},
        "runtime": runtime,
        "replay_note": "Re-run with the same corpus hashes, model, prompts, and retrieval settings, then compare capsules.",
    }
    capsule["capsule_hash"] = _digest(capsule)
    return capsule


def compare_capsules(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Compare two runs without pretending semantic equality is exact."""
    left_sources = {
        (item.get("paper_id"), item.get("chunk_id"), str(item.get("page")))
        for item in left.get("evidence", [])
    }
    right_sources = {
        (item.get("paper_id"), item.get("chunk_id"), str(item.get("page")))
        for item in right.get("evidence", [])
    }
    union = left_sources | right_sources
    citation_jaccard = len(left_sources & right_sources) / len(union) if union else 1.0
    left_score = left.get("trace", {}).get("reliability_score")
    right_score = right.get("trace", {}).get("reliability_score")
    score_delta = None
    if isinstance(left_score, (int, float)) and isinstance(right_score, (int, float)):
        score_delta = round(right_score - left_score, 4)
    return {
        "left_capsule_id": left.get("capsule_id"),
        "right_capsule_id": right.get("capsule_id"),
        "same_answer_hash": left.get("answer_hash") == right.get("answer_hash"),
        "same_evidence_hash": left.get("evidence_hash") == right.get("evidence_hash"),
        "citation_jaccard": round(citation_jaccard, 4),
        "reliability_delta": score_delta,
        "decision_changed": left.get("trace", {}).get("decision") != right.get("trace", {}).get("decision"),
        "added_evidence": [list(item) for item in sorted(right_sources - left_sources)],
        "removed_evidence": [list(item) for item in sorted(left_sources - right_sources)],
    }
