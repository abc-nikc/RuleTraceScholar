"""Tests for model-assisted claim/evidence consistency checks."""

import unittest

from research_audit.semantic_checks import (
    EvidenceConflict,
    SemanticAuditResponse,
    SemanticJudgement,
    run_semantic_evidence_checks,
)


class FakeStructuredLLM:
    def __init__(self, response):
        self.response = response

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return self.response


class SemanticAuditTests(unittest.IsolatedAsyncioTestCase):
    def explanation(self):
        return {"claims": [{
            "claim_id": "C1",
            "text": "Method A reaches 91.2% accuracy.",
            "requires_evidence": True,
            "valid_citation_refs": [1, 2],
            "evidence": [
                {"ref": 1, "excerpt": "Method A reaches 91.2% accuracy."},
                {"ref": 2, "excerpt": "A later run reports 88.1%."},
            ],
        }]}

    async def test_contradictions_and_conflicts_force_conflict_decision(self):
        response = SemanticAuditResponse(
            judgements=[SemanticJudgement(
                claim_id="C1", verdict="contradicted", rationale="The excerpts disagree."
            )],
            conflicts=[EvidenceConflict(
                left_ref=1, right_ref=2, relation="tension", rationale="Different reported values."
            )],
        )
        result = await run_semantic_evidence_checks(FakeStructuredLLM(response), self.explanation())
        self.assertEqual(result["decision"], "conflict")
        self.assertEqual(result["counts"]["contradicted"], 1)
        self.assertEqual(len(result["conflicts"]), 1)

    async def test_claims_without_citations_are_not_sent_to_model(self):
        result = await run_semantic_evidence_checks(
            FakeStructuredLLM(None),
            {"claims": [{"claim_id": "C1", "requires_evidence": True, "valid_citation_refs": []}]},
        )
        self.assertEqual(result["decision"], "unavailable")


if __name__ == "__main__":
    unittest.main()
