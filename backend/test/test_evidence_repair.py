"""Tests for bounded retrieve-rewrite-verify evidence repair."""

import unittest
from types import SimpleNamespace

from langchain_core.documents import Document

from explainability.repair import repair_answer_with_evidence


class FakeRetriever:
    def invoke(self, query, callbacks, paper_ids):
        return [Document(
            page_content="The evaluated method improves evidence coverage.",
            metadata={
                "paper_id": "paper-a",
                "chunk_id": "chunk-1",
                "page_num": 4,
                "section_path": "Results",
                "node_type": "paragraph",
                "retrieval_relevance": 0.9,
            },
        )]


class FakeLLM:
    async def ainvoke(self, messages):
        return SimpleNamespace(content="The method improves evidence coverage [1].")


class ImprovingExplainer:
    def evaluate(self, answer, citations, **kwargs):
        return {
            "decision": "supported",
            "reliability_score": 0.91,
            "claims": [],
        }


class EvidenceRepairTests(unittest.IsolatedAsyncioTestCase):
    async def test_rewrite_is_applied_only_after_trace_improves(self):
        original = {
            "decision": "caution",
            "reliability_score": 0.55,
            "claims": [{
                "claim_id": "C1",
                "text": "The method improves evidence coverage.",
                "requires_evidence": True,
                "grounded": False,
            }],
        }
        result = await repair_answer_with_evidence(
            llm=FakeLLM(),
            retriever_tool=FakeRetriever(),
            explainer=ImprovingExplainer(),
            query="What improves coverage?",
            answer="The method improves evidence coverage.",
            citations=[],
            explanation=original,
            query_type="general",
            sub_query_count=1,
            paper_ids=["paper-a"],
        )
        self.assertTrue(result["repair"]["attempted"])
        self.assertTrue(result["repair"]["applied"])
        self.assertEqual(result["repair"]["added_evidence"], 1)
        self.assertEqual(result["explanation"]["decision"], "supported")

    async def test_no_unsupported_claim_skips_repair(self):
        explanation = {
            "decision": "supported",
            "reliability_score": 0.9,
            "claims": [{"requires_evidence": True, "grounded": True}],
        }
        result = await repair_answer_with_evidence(
            llm=FakeLLM(), retriever_tool=FakeRetriever(), explainer=ImprovingExplainer(),
            query="q", answer="a", citations=[], explanation=explanation,
            query_type="general", sub_query_count=1, paper_ids=[],
        )
        self.assertFalse(result["repair"]["attempted"])
        self.assertFalse(result["repair"]["applied"])


if __name__ == "__main__":
    unittest.main()
