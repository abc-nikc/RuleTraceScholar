"""Regression tests for bounded local-model execution."""

import asyncio
from unittest.mock import Mock, patch

from agent.graph import _focused_sub_queries
from agent.nodes import _answer_language_instruction, _bounded_documents, _sanitize_answer, classify_query, retrieve
from app.routers.chat import _evidence_guard_warning


def test_deep_mode_removes_duplicate_broad_query_and_caps_work():
    original = "Explain architecture, results, and limitations"
    selected = _focused_sub_queries(
        original,
        [original, "architecture", "results", "limitations", "future work"],
        3,
    )

    assert selected == ["architecture", "results", "limitations"]


def test_single_query_is_preserved():
    assert _focused_sub_queries("question", ["question"], 3) == ["question"]


def test_multi_aspect_query_uses_cross_section_route_without_llm_call():
    llm = Mock()
    state = {"query": "请说明核心架构、实验结果和作者承认的局限性"}

    with patch("agent.tools.set_query_type") as set_query_type:
        result = asyncio.run(classify_query(state, llm))

    assert result == {"query_type": "general"}
    set_query_type.assert_called_once_with("general")
    llm.with_structured_output.assert_not_called()


def test_chinese_question_adds_strict_output_language_instruction():
    assert "entirely in Chinese" in _answer_language_instruction("请用中文回答")
    assert _answer_language_instruction("Answer in English") == ""


def test_fast_context_is_bounded_without_dropping_citation_slots():
    documents = [f"start-{index}-" + ("x" * 3000) + f"-end-{index}" for index in range(5)]
    bounded = _bounded_documents(documents, 3500)

    assert len(bounded) == len(documents)
    assert sum(len(item) for item in bounded) < 4000
    assert all(f"start-{index}" in item and f"end-{index}" in item for index, item in enumerate(bounded))


def test_multi_aspect_retrieval_stays_cross_section():
    retriever = Mock()
    retriever.invoke.return_value = []
    state = {
        "query": "请说明核心架构、主要实验结果和作者承认的局限性",
        "query_type": "general",
        "paper_ids": ["paper-1"],
    }

    asyncio.run(retrieve(state, retriever, Mock()))

    assert retriever.invoke.call_args.kwargs["section_type_filter"] is None
    assert retriever.invoke.call_args.kwargs["rerank"] is None
    assert retriever.invoke.call_args.kwargs["expand_parent"] is None


def test_fast_retrieval_disables_expensive_reranker():
    retriever = Mock()
    retriever.invoke.return_value = []
    state = {
        "query": "请概述这篇论文",
        "query_type": "general",
        "paper_ids": ["paper-1"],
        "fast_mode": True,
    }

    asyncio.run(retrieve(state, retriever, Mock()))

    assert retriever.invoke.call_args.kwargs["rerank"] is False
    assert retriever.invoke.call_args.kwargs["expand_parent"] is False


def test_answer_sanitizer_removes_unsupported_strength_and_meta_claim():
    answer = (
        "结果取得显著提升 [1]。\n"
        "所有事实均有证据编号支持。\n"
        "以上事实均基于论文提供的上下文信息。"
    )
    citations = [{"evidence_excerpt": "The method reports consistent gains."}]

    sanitized = _sanitize_answer(answer, citations)

    assert "显著" not in sanitized
    assert "所有事实" not in sanitized
    assert "未引入外部知识" not in sanitized
    assert "以上事实" not in sanitized
    assert "提升 [1]" in sanitized


def test_answer_sanitizer_distinguishes_future_work_from_explicit_limitations():
    answer = (
        "作者承认的局限性包括：\n"
        "- 当前模型在长时程自我进化方面的假定能力较弱，需要进一步加强假定验证 [1]。\n"
        "- 对长时程自我演化进行假证 [1]。\n"
        "- 需要 tighter 的多模态接地 [1]。\n"
        "The provided context does not contain sufficient information to answer this question regarding the specific limitations of the paper."
    )
    citations = [{"evidence_excerpt": "Future work includes stronger falsification."}]

    sanitized = _sanitize_answer(answer, citations, "请说明作者承认的局限")

    assert "列为未来工作" in sanitized
    assert "列为未来工作 [1]" in sanitized
    assert "证伪检验" in sanitized
    assert "证伪能力较弱" not in sanitized
    assert "假证" not in sanitized
    assert "更紧密的多模态接地" in sanitized
    assert "不能把这些未来方向" in sanitized
    assert "The provided context" not in sanitized


def test_evidence_guard_uses_question_language():
    assert "证据发布防护" in _evidence_guard_warning("请用中文回答", blocked=True)
    assert "Evidence review notice" in _evidence_guard_warning("Answer in English", blocked=False)


def test_answer_sanitizer_preserves_stable_ranking_meaning():
    answer = "绝对性能受底层模型限制，导致在不同设置下性能保持稳定 [1]。"
    citations = [{"evidence_excerpt": "Absolute performance is bounded by the backbone LLM, producing a stable ranking across settings."}]

    sanitized = _sanitize_answer(answer, citations, "请说明实验结果")

    assert "形成稳定的性能排序" in sanitized
