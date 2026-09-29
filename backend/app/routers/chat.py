"""Chat API — SSE streaming with session management."""

import json
import uuid
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field

from config import Config
from app.runtime_settings import get_runtime_settings
from app.dependencies import get_llm, get_retriever_tool, get_checkpointer
from app.store import create_session, get_session, save_capsule, update_session
from agent.graph import build_graph
from rag.citation import CitationExtractor
from explainability import EvidenceRuleEngine, repair_answer_with_evidence
from research_audit import build_capsule, run_claim_unit_tests, run_semantic_evidence_checks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])
explainer = EvidenceRuleEngine()


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    paper_ids: list[str] = Field(default_factory=list, max_length=10)


def _public_citations(citations: list[dict]) -> list[dict]:
    """Remove internal VLM paths while retaining auditable provenance."""
    allowed = {
        "paper_id",
        "section",
        "page",
        "chunk_id",
        "node_type",
        "retrieval_rank",
        "retrieval_relevance",
        "evidence_excerpt",
    }
    return [{key: value for key, value in citation.items() if key in allowed} for citation in citations]


def _build_graph():
    return build_graph(
        llm=get_llm(),
        retriever=get_retriever_tool(),
        citation_extractor=CitationExtractor,
        max_retries=Config.MAX_RETRIES,
        checkpointer=get_checkpointer(),
    )


async def _stream_response(
    graph,
    query: str,
    session_id: str,
    paper_ids: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    config = {"configurable": {"thread_id": session_id}}
    graph_input = {"query": query, "paper_ids": paper_ids or []}

    yield json.dumps({"type": "session_id", "data": session_id})
    yield json.dumps({"type": "status", "data": "analyzing"})

    try:
        synth_msgs = []
        final_citations = []
        final_sub_queries = []
        query_type = "general"
        sub_query_count = 1

        async for chunk in graph.astream(graph_input, config=config, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                if node_name == "analyze":
                    sq = node_output.get("sub_queries", [])
                    if sq:
                        final_sub_queries = sq
                        sub_query_count = len(sq)
                        yield json.dumps({"type": "sub_queries", "data": sq})
                        yield json.dumps({"type": "status", "data": "searching"})

                if node_name == "classify":
                    query_type = node_output.get("query_type", "general")

                if node_name == "prepare_synthesis":
                    synth_msgs = node_output.get("synth_messages", [])
                    final_citations = node_output.get("citations", [])
                    logger.info(f"prepare_synthesis: {len(final_citations)} citations")

        llm = get_llm()
        answer_buf = ""
        if synth_msgs:
            async for token in llm.astream(synth_msgs):
                if token.content:
                    answer_buf += token.content
                    yield json.dumps({"type": "answer", "data": answer_buf})

        if not answer_buf:
            yield json.dumps({"type": "answer", "data": ""})

        explanation = explainer.evaluate(
            answer_buf,
            final_citations,
            query_type=query_type,
            sub_query_count=sub_query_count,
        )

        repair = {"attempted": False, "applied": False}
        has_unsupported_claims = any(
            claim.get("requires_evidence") and not claim.get("grounded")
            for claim in explanation.get("claims", [])
        )
        if Config.AUTO_EVIDENCE_REPAIR and (
            explanation["decision"] != "supported" or has_unsupported_claims
        ):
            yield json.dumps({"type": "status", "data": "repairing_evidence"})
            try:
                repair_result = await repair_answer_with_evidence(
                    llm=llm,
                    retriever_tool=get_retriever_tool(),
                    explainer=explainer,
                    query=query,
                    answer=answer_buf,
                    citations=final_citations,
                    explanation=explanation,
                    query_type=query_type,
                    sub_query_count=sub_query_count,
                    paper_ids=paper_ids or [],
                    max_queries=Config.AUTO_EVIDENCE_REPAIR_MAX_QUERIES,
                )
                repair = repair_result["repair"]
                if repair["applied"]:
                    answer_buf = repair_result["answer"]
                    final_citations = repair_result["citations"]
                    explanation = repair_result["explanation"]
                    yield json.dumps({"type": "answer", "data": answer_buf})
            except Exception as exc:
                logger.exception("Optional evidence repair failed")
                repair = {
                    "attempted": True,
                    "applied": False,
                    "detail": str(exc),
                    "before_decision": explanation.get("decision"),
                    "before_score": explanation.get("reliability_score"),
                }

        public_citations = _public_citations(final_citations)
        claim_tests = run_claim_unit_tests(explanation)
        if Config.ENABLE_SEMANTIC_AUDIT:
            yield json.dumps({"type": "status", "data": "auditing_evidence"})
            try:
                semantic_checks = await run_semantic_evidence_checks(llm, explanation)
            except Exception as exc:
                logger.exception("Optional semantic evidence audit failed")
                semantic_checks = {
                    "method": "model-assisted semantic evidence review",
                    "decision": "unavailable",
                    "judgements": [],
                    "conflicts": [],
                    "detail": str(exc),
                    "limitations": ["Semantic review failed; deterministic checks remain available."],
                }
            claim_tests["semantic_checks"] = semantic_checks
            if semantic_checks["decision"] == "conflict":
                claim_tests["decision"] = "fail"
            elif semantic_checks["decision"] == "review" and claim_tests["decision"] == "pass":
                claim_tests["decision"] = "review"

        semantic_decision = (claim_tests.get("semantic_checks") or {}).get("decision")
        if (
            explanation["decision"] == "insufficient"
            or claim_tests["decision"] == "fail"
            or semantic_decision == "conflict"
        ):
            claim_tests["release_decision"] = "blocked"
        elif explanation["decision"] == "caution" or claim_tests["decision"] == "review":
            claim_tests["release_decision"] = "review"
        else:
            claim_tests["release_decision"] = "supported"

        if Config.EXPLANATION_GUARD_ENABLED and claim_tests["release_decision"] != "supported":
            if claim_tests["release_decision"] == "blocked":
                warning = (
                    "\n\n> Evidence release guard: one or more claim/citation checks failed. "
                    "Treat the answer as unverified and inspect the TRACE and semantic audit panels."
                )
            else:
                warning = (
                    "\n\n> Evidence review notice: some claims require manual review. "
                    "Inspect the TRACE and semantic audit panels before relying on them."
                )
            answer_buf += warning
            yield json.dumps({"type": "answer", "data": answer_buf})

        runtime_settings = get_runtime_settings()
        capsule = build_capsule(
            session_id=session_id,
            query=query,
            answer=answer_buf,
            citations=public_citations,
            explanation=explanation,
            claim_tests=claim_tests,
            query_type=query_type,
            sub_query_count=sub_query_count,
            repair=repair,
            runtime={
                "llm_model": Config.LLM_MODEL,
                "embedding_model": Config.EMBEDDING_MODEL,
                "reranker_model": Config.RERANKER_MODEL,
                "top_k": runtime_settings.retrieval.top_k,
                "fetch_k": runtime_settings.retrieval.fetch_k,
                "rrf_k": runtime_settings.retrieval.rrf_k,
                "rerank": runtime_settings.retrieval.rerank,
                "expand_parent": runtime_settings.retrieval.expand_parent,
                "evidence_diversity": runtime_settings.retrieval.diversify,
                "diversity_weight": runtime_settings.retrieval.diversity_weight,
                "chunking": runtime_settings.chunking.model_dump(),
                "memory": runtime_settings.memory.model_dump(),
            },
        )
        save_capsule(capsule)

        await graph.aupdate_state(config, {
            "messages": [
                HumanMessage(content=query),
                AIMessage(
                    content=answer_buf,
                    additional_kwargs={
                        "citations": public_citations,
                        "explanation": explanation,
                        "claim_tests": claim_tests,
                        "repair": repair,
                        "sub_queries": final_sub_queries,
                        "capsule": {
                            "capsule_id": capsule["capsule_id"],
                            "capsule_hash": capsule["capsule_hash"],
                        },
                    },
                ),
            ],
            "answer": answer_buf,
        })

        yield json.dumps({"type": "citations", "data": public_citations})
        yield json.dumps({"type": "explanation", "data": explanation})
        yield json.dumps({"type": "claim_tests", "data": claim_tests})
        yield json.dumps({"type": "repair", "data": repair})
        yield json.dumps({"type": "capsule", "data": {
            "capsule_id": capsule["capsule_id"],
            "capsule_hash": capsule["capsule_hash"],
        }})

        title_hint = query[:50] + ("…" if len(query) > 50 else "")
        session = get_session(session_id)
        if session and not session.get("title"):
            update_session(session_id, title=title_hint)

        yield json.dumps({"type": "done", "data": None})

    except Exception as e:
        logger.exception("Chat error")
        yield json.dumps({"type": "error", "data": str(e)})


@router.post("/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())

    if not get_session(session_id):
        create_session(session_id)

    graph = _build_graph()

    return EventSourceResponse(
        _stream_response(graph, req.query, session_id, req.paper_ids),
        media_type="text/event-stream",
    )
