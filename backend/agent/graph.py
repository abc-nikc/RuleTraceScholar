"""Graph assembly for the multi-agent RAG system."""

from typing import Optional

from config import Config
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Send

from .states import AgentState, SubAgentState, SubAnswer
from .nodes import (
    analyze_query,
    classify_query,
    prepare_synthesis,
    summarize_conversation,
    retrieve,
    generate,
    reflect,
    should_retry,
    prepare_retry,
)


def _focused_sub_queries(original: str, proposed: list[str], limit: int) -> list[str]:
    queries = proposed or [original]
    if len(queries) > 1:
        focused = [query for query in queries if query != original]
        if focused:
            queries = focused
    return queries[:max(1, limit)]


def _collect_sub_answer(state: SubAgentState) -> dict:
    return {
        "sub_answers": [SubAnswer(
            query=state["query"],
            answer=state.get("answer", ""),
            citations=state.get("citations", []),
        )]
    }


def _build_sub_agent_graph(
    llm: BaseChatModel,
    retriever,
    citation_extractor,
    max_retries: int,
    vision_service=None,
) -> StateGraph:
    sg = StateGraph(SubAgentState)

    async def retrieve_node(state: SubAgentState) -> dict:
        return await retrieve(state, retriever=retriever, citation_extractor=citation_extractor)

    async def generate_node(state: SubAgentState) -> dict:
        return await generate(state, llm=llm, vision_service=vision_service)

    async def reflect_node(state: SubAgentState) -> dict:
        return await reflect(state, llm=llm, vision_service=vision_service)

    def retry_router(state: SubAgentState) -> str:
        return should_retry(state, max_retries=max_retries)

    sg.add_node("retrieve", retrieve_node)
    sg.add_node("generate", generate_node)
    sg.add_node("reflect", reflect_node)
    sg.add_node("prepare_retry", prepare_retry)

    sg.add_edge(START, "retrieve")
    sg.add_edge("retrieve", "generate")
    sg.add_edge("generate", "reflect")
    sg.add_conditional_edges("reflect", retry_router, {
        "retry": "prepare_retry",
        "done": END,
    })
    sg.add_edge("prepare_retry", "retrieve")

    return sg


def build_graph(
    llm: BaseChatModel,
    retriever,
    citation_extractor,
    max_retries: int = 2,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    vision_service=None,
    deep_analysis: bool = False,
    max_sub_queries: int = 3,
):
    def dispatch(state: AgentState):
        queries = state["sub_queries"][:max(1, max_sub_queries)]
        return [Send("sub_agent", {
            "query": q,
            "query_type": state.get("query_type", "general"),
            "paper_ids": state.get("paper_ids", []),
        }) for q in queries]

    async def sub_agent_node(state: dict) -> dict:
        sub_graph = _build_sub_agent_graph(llm, retriever, citation_extractor, max_retries, vision_service).compile()
        sub_input = {
            "query": state["query"],
            "paper_ids": state.get("paper_ids", []),
            "query_type": state.get("query_type", "general"),
            "documents": [],
            "answer": "",
            "citations": [],
            "is_sufficient": False,
            "retry_queries": [],
            "retries": 0,
            "needs_vlm": False,
            # Bound prompt evaluation in fast mode. Deep mode keeps full context.
            "context_char_limit": (
                Config.DEEP_CONTEXT_CHAR_LIMIT
                if deep_analysis
                else Config.FAST_CONTEXT_CHAR_LIMIT
            ),
            "fast_mode": not deep_analysis,
        }
        result = await sub_graph.ainvoke(sub_input)
        return _collect_sub_answer(result)

    async def summarize_node(state: AgentState) -> dict:
        return await summarize_conversation(state, llm=llm)

    async def classify_node(state: AgentState) -> dict:
        return await classify_query(state, llm=llm)

    async def analyze_node(state: AgentState) -> dict:
        if not deep_analysis:
            return {"sub_queries": [state["query"]]}
        result = await analyze_query(state, llm=llm)
        queries = _focused_sub_queries(
            state["query"],
            result.get("sub_queries", [state["query"]]),
            max_sub_queries,
        )
        return {"sub_queries": queries}

    graph = StateGraph(AgentState)

    graph.add_node("summarize", summarize_node)
    graph.add_node("classify", classify_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("sub_agent", sub_agent_node)
    graph.add_node("prepare_synthesis", prepare_synthesis)

    graph.add_edge(START, "summarize")
    graph.add_edge("summarize", "classify")
    graph.add_edge("classify", "analyze")
    graph.add_conditional_edges("analyze", dispatch, ["sub_agent"])
    graph.add_edge("sub_agent", "prepare_synthesis")
    graph.add_edge("prepare_synthesis", END)

    return graph.compile(checkpointer=checkpointer)
