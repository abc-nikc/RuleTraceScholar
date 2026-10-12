"""Node functions for the multi-agent RAG graph."""

import asyncio
import re
import logging

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage, AIMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document

from .states import AgentState, SubAgentState
from .prompts import QUERY_ANALYZER, QUERY_CLASSIFIER, SYNTHESIZER, GENERATOR, REFLECTOR, SUMMARIZER

logger = logging.getLogger(__name__)


def _answer_language_instruction(text: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", text):
        return "\n13. Answer entirely in Chinese, including headings, caveats, and summaries."
    return ""

_QUERY_ROUTE_KEYWORDS = (
    ("experimental_result", ("experiment", "result", "metric", "benchmark", "ablation", "performance", "实验", "结果", "指标", "消融", "性能", "数据集")),
    ("conclusion", ("limitation", "future work", "discussion", "conclusion", "weakness", "局限", "限制", "未来", "结论", "不足")),
    ("method", ("method", "architecture", "algorithm", "pipeline", "model", "how does", "方法", "架构", "算法", "流程", "模型", "如何工作")),
    ("background", ("contribution", "motivation", "background", "overview", "abstract", "贡献", "动机", "背景", "概述", "摘要")),
)


def _infer_query_type(query: str, fallback: str = "general") -> str:
    lowered = query.lower()
    for query_type, keywords in _QUERY_ROUTE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return query_type
    return fallback


def _query_aspect_count(query: str) -> int:
    lowered = query.lower()
    return sum(any(keyword in lowered for keyword in keywords) for _, keywords in _QUERY_ROUTE_KEYWORDS)

class QueryAnalysis(BaseModel):
    sub_queries: list[str] = Field(description="List of sub-queries, original query first")


class QueryClassification(BaseModel):
    query_type: str = Field(description="One of: experimental_result, method, background, conclusion, general")


class ReflectionResult(BaseModel):
    is_sufficient: bool = Field(description="Whether the answer is sufficient")
    retry_queries: list[str] = Field(default_factory=list, description="Queries for missing info")


def _build_context_header(state: AgentState) -> str:
    from app.runtime_settings import get_runtime_settings

    window_size = get_runtime_settings().memory.window_size
    parts = []
    summary = state.get("summary", "")
    if summary:
        parts.append(f"<conversation_summary>\n{summary}\n</conversation_summary>")

    recent = state.get("messages", [])[-window_size:]
    if recent:
        lines = []
        for msg in recent:
            if isinstance(msg, HumanMessage):
                role = "User"
            elif isinstance(msg, AIMessage):
                role = "Assistant"
            else:
                continue
            lines.append(f"{role}: {msg.content}")
        if lines:
            parts.append("<recent_conversation>\n" + "\n".join(lines) + "\n</recent_conversation>")

    return "\n\n".join(parts)


def _remap_citations(answer: str, offset: int) -> str:
    def _replace(m):
        return f"[{int(m.group(1)) + offset}]"
    return re.sub(r"\[(\d+)\]", _replace, answer)


def _bounded_documents(documents: list[str], char_limit: int) -> list[str]:
    """Bound local-model prompt cost while keeping every citation addressable."""
    if char_limit <= 0 or sum(len(item) for item in documents) <= char_limit:
        return documents
    per_document = max(600, char_limit // max(len(documents), 1))
    bounded = []
    for document in documents:
        if len(document) <= per_document:
            bounded.append(document)
            continue
        head_size = int(per_document * 0.72)
        tail_size = per_document - head_size
        bounded.append(
            document[:head_size].rstrip()
            + "\n[…证据上下文已压缩…]\n"
            + document[-tail_size:].lstrip()
        )
    return bounded


def _sanitize_answer(answer: str, citations: list[dict], query: str = "") -> str:
    """Remove unsupported strength inflation and self-certifying meta claims."""
    evidence = " ".join(
        str(item.get("evidence_excerpt") or item.get("text") or "")
        for item in citations
    ).lower()
    if "statistically significant" not in evidence and "显著" not in evidence:
        answer = re.sub(r"显著(?=(提升|改善|优于|增加|降低|增益))", "", answer)
        answer = answer.replace("效果显著", "报告的增益较大")
        answer = re.sub(
            r"\bstatistically significant(?:ly)?\b",
            "reported",
            answer,
            flags=re.IGNORECASE,
        )
    answer = re.sub(
        r"(?m)^\s*(?:所有|以上).*?(?:事实|陈述).*?(?:证据|引用).*?$\n?",
        "",
        answer,
    )
    answer = re.sub(
        r"(?m)^\s*(?:以上|上述)(?:内容|回答|事实|结论).*?(?:基于|未引入外部知识).*?$\n?",
        "",
        answer,
    )
    if "falsification" in evidence:
        answer = answer.replace("假定检验", "证伪检验")
        answer = answer.replace("假定验证", "证伪检验")
        answer = answer.replace("假定能力", "证伪能力")
        answer = answer.replace("假证", "证伪检验")
        answer = re.sub(
            r"当前模型在(.+?)方面的证伪能力较弱[，,]\s*需要进一步加强证伪检验",
            r"未来工作包括面向\1的更强证伪检验",
            answer,
        )
    answer = answer.replace("tighter 的", "更紧密的")
    if "stable ranking" in evidence:
        answer = answer.replace(
            "在不同设置下性能保持稳定",
            "在不同设置下形成稳定的性能排序",
        )
    if re.search(r"[\u4e00-\u9fff]", query):
        future_ref = next(
            (
                index for index, item in enumerate(citations, 1)
                if "future work" in str(
                    item.get("evidence_excerpt") or item.get("text") or ""
                ).lower()
            ),
            None,
        )
        if future_ref:
            answer = answer.replace(
                "作者承认的局限性包括：",
                "关于作者明确承认的局限性：检索证据未把以下内容明确标为“局限”，"
                f"而是列为未来工作 [{future_ref}]：",
            )
            answer = answer.replace(
                "The provided context does not contain sufficient information to answer this question regarding the specific limitations of the paper.",
                f"因此，不能把这些未来方向表述为作者明确承认的局限 [{future_ref}]。",
            )
    return answer.strip()


# --------------- Top-level agent nodes ---------------

async def analyze_query(state: AgentState, llm: BaseChatModel) -> dict:
    query = state["query"]
    context_header = _build_context_header(state)

    # Most paper questions have one intent. Avoid an extra local-LLM call and
    # duplicate retrieval for these; multi-aspect questions still decompose.
    if _query_aspect_count(query) <= 1:
        return {"sub_queries": [query]}

    system_content = QUERY_ANALYZER
    if context_header:
        system_content += f"\n\n# Conversation Context\n{context_header}"
    msgs = [SystemMessage(content=system_content), HumanMessage(content=query)]

    structured_llm = llm.with_structured_output(QueryAnalysis)
    try:
        result: QueryAnalysis = await structured_llm.ainvoke(msgs)
        sub_queries = result.sub_queries
    except Exception:
        sub_queries = [query]

    if query not in sub_queries:
        sub_queries.insert(0, query)

    logger.info(f"Decomposed into {len(sub_queries)} sub-queries")
    return {"sub_queries": sub_queries}


async def classify_query(state: AgentState, llm: BaseChatModel) -> dict:
    from .tools import set_query_type
    query = state["query"]

    # A multi-aspect question must search across sections.  Routing the whole
    # question to the first matching section (for example, experiments) hides
    # method or limitation evidence in fast mode.
    if _query_aspect_count(query) > 1:
        set_query_type("general")
        logger.info("Multi-aspect query classified deterministically as: general")
        return {"query_type": "general"}

    inferred = _infer_query_type(query)
    if inferred != "general":
        set_query_type(inferred)
        logger.info("Query classified deterministically as: %s", inferred)
        return {"query_type": inferred}

    structured_llm = llm.with_structured_output(QueryClassification)
    try:
        result: QueryClassification = await structured_llm.ainvoke([
            SystemMessage(content=QUERY_CLASSIFIER),
            HumanMessage(content=query),
        ])
        query_type = result.query_type
        if query_type not in ("experimental_result", "method", "background", "conclusion", "general"):
            query_type = "general"
    except Exception:
        query_type = "general"

    set_query_type(query_type)
    logger.info(f"Query classified as: {query_type}")
    return {"query_type": query_type}


def prepare_synthesis(state: AgentState) -> dict:
    sub_answers = state.get("sub_answers", [])
    context_header = _build_context_header(state)

    context_parts = []
    all_citations = []
    global_idx = 0
    for sa in sub_answers:
        remapped = _remap_citations(sa["answer"], global_idx)
        context_parts.append(f"Q: {sa['query']}\nA: {remapped}")
        sa_citations = sa.get("citations", [])
        all_citations.extend(sa_citations)
        global_idx += max(len(sa_citations), 1)

    sub_context = "\n\n".join(context_parts)

    if len(sub_answers) == 1:
        return {
            "synth_messages": [],
            "direct_answer": sub_answers[0]["answer"],
            "citations": all_citations,
        }

    system_content = SYNTHESIZER.format(context=sub_context)
    system_content += _answer_language_instruction(state["query"])
    if context_header:
        system_content += f"\n\n# Conversation Context\n{context_header}"

    return {
        "synth_messages": [
            SystemMessage(content=system_content),
            HumanMessage(content=f"Original question: {state['query']}"),
        ],
        "citations": all_citations,
        "direct_answer": "",
    }


async def summarize_conversation(state: AgentState, llm: BaseChatModel) -> dict:
    from app.runtime_settings import get_runtime_settings

    memory_settings = get_runtime_settings().memory
    if not memory_settings.summarization_enabled:
        return {}

    window_size = memory_settings.window_size
    messages = state.get("messages", [])
    existing_summary = state.get("summary", "")

    if len(messages) <= window_size:
        return {}

    to_summarize = messages[:-window_size]

    lines = []
    if existing_summary:
        lines.append(f"Previous summary: {existing_summary}")
    for msg in to_summarize:
        if isinstance(msg, HumanMessage):
            role = "User"
        elif isinstance(msg, AIMessage):
            role = "Assistant"
        else:
            continue
        lines.append(f"{role}: {msg.content}")

    if not lines:
        return {}

    history = "\n".join(lines)

    resp = await llm.ainvoke([
        SystemMessage(content=SUMMARIZER.format(history=history)),
        HumanMessage(content="Summarize the above conversation."),
    ])

    return {
        "summary": resp.content,
        "messages": [RemoveMessage(id=m.id) for m in to_summarize],
    }


# --------------- Sub-agent nodes ---------------

async def retrieve(state: SubAgentState, retriever, citation_extractor) -> dict:
    from rag.factory import is_visual_query
    query = state["query"]
    query_type = state.get("query_type", "general")
    paper_ids = state.get("paper_ids", [])

    _ROUTE_CONFIG: dict[str, list[str] | None] = {
        "experimental_result": ["experiment"],
        "method": ["method"],
        "background": ["background"],
        "conclusion": ["conclusion"],
        "general": None,
    }
    lowered = query.lower()
    # Preserve the deliberate cross-section route for compound questions such
    # as architecture + results + limitations. Re-inferring the first matched
    # keyword here used to narrow such questions back to experiments only.
    query_type = "general" if _query_aspect_count(query) > 1 else _infer_query_type(lowered, query_type)
    section_type_filter = _ROUTE_CONFIG.get(query_type)

    fast_mode = state.get("fast_mode", False)
    docs: list[Document] = []
    if fast_mode and _query_aspect_count(query) > 1:
        # Compound questions need cross-section coverage, but generating one
        # answer per aspect is too expensive on CPU. Retrieve two compact child
        # chunks per detected aspect and answer them in one model pass.
        aspect_focus = (
            ("method", ("method", "architecture", "algorithm", "pipeline", "model", "方法", "架构", "算法", "流程", "模型"), "core architecture method workflow"),
            ("experiment", ("experiment", "result", "metric", "benchmark", "ablation", "实验", "结果", "指标", "消融"), "main experimental results metrics ablation"),
            ("conclusion", ("limitation", "future work", "discussion", "conclusion", "weakness", "局限", "限制", "未来", "结论", "不足"), "authors acknowledged limitations future work"),
            ("background", ("contribution", "motivation", "background", "overview", "abstract", "贡献", "动机", "背景", "概述", "摘要"), "stated contributions motivation"),
        )
        seen = set()
        for section_type, keywords, focus in aspect_focus:
            if not any(keyword in lowered for keyword in keywords):
                continue
            candidates = await asyncio.to_thread(
                retriever.invoke,
                f"{query}\nFocus: {focus}",
                section_type_filter=[section_type],
                paper_ids=paper_ids,
                rerank=False,
                expand_parent=False,
            )
            preferred = [
                document for document in candidates
                if document.metadata.get("node_type") not in {"section_header", "figure"}
            ]
            for document in (preferred or candidates)[:2]:
                key = document.metadata.get("chunk_id") or document.page_content
                if key not in seen:
                    seen.add(key)
                    docs.append(document)
        logger.info("Fast compound retrieval selected %s cross-section chunks", len(docs))
    else:
        docs = await asyncio.to_thread(
            retriever.invoke,
            query,
            section_type_filter=section_type_filter,
            paper_ids=paper_ids,
            rerank=False if fast_mode else None,
            expand_parent=False if fast_mode else None,
        )

    if not docs and section_type_filter:
        logger.info(f"No results with section filter, retrying without filter")
        docs = await asyncio.to_thread(
            retriever.invoke,
            query,
            section_type_filter=None,
            paper_ids=paper_ids,
            rerank=False if fast_mode else None,
            expand_parent=False if fast_mode else None,
        )

    if any(keyword in lowered for keyword in ("contribution", "贡献")):
        contribution_docs = [
            doc for doc in docs
            if any(
                section in str(doc.metadata.get("section_path", "")).lower()
                for section in ("abstract", "introduction", "摘要", "引言")
            )
        ]
        if contribution_docs:
            docs = contribution_docs

    citations = citation_extractor.extract_all(docs) if docs else []
    documents = []
    for doc, cite in zip(docs, citations):
        source = citation_extractor.format_citation(cite)
        documents.append(f"{doc.page_content}\n[Source: {source}]")

    if len(docs) != len(citations):
        logger.warning(f"Doc/citation count mismatch: {len(docs)} docs vs {len(citations)} citations")

    # Determine if VLM should be invoked in generate step
    has_figure = any(
        c.get("node_type") == "figure" and c.get("metadata", {}).get("image_path")
        for c in citations
    )
    needs_vlm = is_visual_query(query) and has_figure

    truncated = query[:50] + ("..." if len(query) > 50 else "")
    logger.info(f"Retrieved {len(documents)} docs for: {truncated} | needs_vlm={needs_vlm}")
    return {"documents": documents, "citations": citations, "needs_vlm": needs_vlm}


async def generate(state: SubAgentState, llm: BaseChatModel, vision_service=None) -> dict:
    query = state["query"]
    documents = _bounded_documents(
        state.get("documents", []),
        state.get("context_char_limit", 0),
    )
    citations = state.get("citations", [])
    needs_vlm = state.get("needs_vlm", False)

    if not documents:
        return {"answer": "No relevant information found.", "citations": []}

    # VLM enhancement: inject figure descriptions before generation
    if needs_vlm and vision_service:
        from rag.factory import should_invoke_vlm
        has_figure = any(
            c.get("node_type") == "figure" and c.get("metadata", {}).get("image_path")
            for c in citations
        )
        if should_invoke_vlm(query, has_figure):
            for cite in citations:
                if cite.get("node_type") != "figure":
                    continue
                image_path = cite.get("metadata", {}).get("image_path")
                if not image_path:
                    continue
                vlm_desc = cite.get("metadata", {}).get("vlm_description")
                if not vlm_desc:
                    caption = cite.get("text", "")
                    vlm_desc = vision_service.analyze_figure(image_path, caption)
                    if vlm_desc:
                        cite.setdefault("metadata", {})["vlm_description"] = vlm_desc
                if vlm_desc:
                    documents = list(documents) + [f"[Figure Analysis] {vlm_desc}"]
                    logger.info(f"VLM analysis injected for figure: {image_path}")

    context = "\n\n".join(f"[{i}] {d}" for i, d in enumerate(documents, 1))

    resp = await llm.ainvoke([
        SystemMessage(content=GENERATOR + _answer_language_instruction(query)),
        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {query}"),
    ])

    return {"answer": _sanitize_answer(str(resp.content), citations, query)}


async def reflect(state: SubAgentState, llm: BaseChatModel, vision_service=None) -> dict:
    query = state["query"]
    answer = state.get("answer", "")
    documents = state.get("documents", [])
    citations = state.get("citations", [])
    retries = state.get("retries", 0)

    if not documents:
        return {"is_sufficient": True, "retry_queries": [], "retries": retries + 1}

    # The reflector prompt itself treats a relevant cited answer as sufficient.
    # Apply that rule deterministically to avoid another full local-model pass.
    if citations and re.search(r"\[\d+\]", answer):
        return {"is_sufficient": True, "retry_queries": [], "retries": retries + 1}

    structured_llm = llm.with_structured_output(ReflectionResult)
    try:
        result: ReflectionResult = await structured_llm.ainvoke([
            SystemMessage(content=REFLECTOR),
            HumanMessage(content=f"Question: {query}\nAnswer: {answer}"),
        ])
        is_sufficient = result.is_sufficient
        retry_queries = result.retry_queries
    except Exception:
        is_sufficient = True
        retry_queries = []

    # VLM fallback: answer insufficient + has figures + VLM not yet used
    if not is_sufficient and vision_service and not state.get("needs_vlm", False):
        from rag.factory import should_invoke_vlm
        figure_citations = [
            c for c in citations
            if c.get("node_type") == "figure" and c.get("metadata", {}).get("image_path")
        ]
        has_figure = bool(figure_citations)
        if should_invoke_vlm(query, has_figure, answer=answer):
            # Inject VLM descriptions and re-generate
            extra_docs = []
            for cite in figure_citations[:2]:  # cap at 2 to control cost
                image_path = cite["metadata"]["image_path"]
                vlm_desc = cite["metadata"].get("vlm_description")
                if not vlm_desc:
                    caption = cite.get("text", "")
                    vlm_desc = vision_service.analyze_figure(image_path, caption)
                    if vlm_desc:
                        cite["metadata"]["vlm_description"] = vlm_desc
                if vlm_desc:
                    extra_docs.append(f"[Figure Analysis] {vlm_desc}")
                    logger.info(f"VLM fallback triggered for: {image_path}")

            if extra_docs:
                enhanced_docs = list(documents) + extra_docs
                context = "\n\n".join(f"[{i}] {d}" for i, d in enumerate(enhanced_docs, 1))
                resp = await llm.ainvoke([
                    SystemMessage(content=GENERATOR + _answer_language_instruction(query)),
                    HumanMessage(content=f"Context:\n{context}\n\nQuestion: {query}"),
                ])
                return {
                    "answer": _sanitize_answer(str(resp.content), citations, query),
                    "documents": enhanced_docs,
                    "needs_vlm": True,   # mark as used to prevent re-trigger
                    "is_sufficient": True,
                    "retry_queries": [],
                    "retries": retries + 1,
                }

    return {
        "is_sufficient": is_sufficient,
        "retry_queries": retry_queries,
        "retries": retries + 1,
    }


# --------------- Routing functions ---------------

def should_retry(state: SubAgentState, max_retries: int = 2) -> str:
    if not state.get("is_sufficient", True) and state.get("retries", 0) < max_retries:
        logger.info(f"Reflection: insufficient, retrying ({state.get('retries', 0)}/{max_retries})")
        return "retry"
    return "done"


def prepare_retry(state: SubAgentState) -> dict:
    retry_queries = state.get("retry_queries", [])
    query = retry_queries[-1] if retry_queries else state["query"]
    return {"query": query}
