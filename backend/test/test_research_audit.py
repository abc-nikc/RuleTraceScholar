"""Tests for replay capsules, deterministic checks, and portable storage."""

import tempfile
import unittest
from pathlib import Path

from app import store
from research_audit import build_capsule, compare_capsules, run_claim_unit_tests


class ResearchAuditTests(unittest.TestCase):
    def setUp(self):
        self.explanation = {
            "decision": "supported",
            "reliability_score": 0.82,
            "metrics": {"citation_coverage": 1.0},
            "rule_trace": [],
            "claims": [{
                "claim_id": "C1",
                "text": "Accuracy improved by 12%.",
                "requires_evidence": True,
                "valid_citation_refs": [1],
                "invalid_citation_refs": [],
                "evidence": [{"excerpt": "The reported accuracy improved by 12%."}],
            }],
        }

    def test_numeric_claim_test_passes_when_value_is_in_evidence(self):
        result = run_claim_unit_tests(self.explanation)
        self.assertEqual(result["decision"], "pass")
        self.assertEqual(result["counts"]["pass"], 2)

    def test_replay_comparison_reports_evidence_change(self):
        tests = run_claim_unit_tests(self.explanation)
        left = build_capsule(
            session_id="s1", query="q", answer="a",
            citations=[{"paper_id": "p1", "chunk_id": "c1"}],
            explanation=self.explanation, claim_tests=tests,
            query_type="general", sub_query_count=1, runtime={"model": "test"},
        )
        right = build_capsule(
            session_id="s1", query="q", answer="b",
            citations=[{"paper_id": "p2", "chunk_id": "c2"}],
            explanation=self.explanation, claim_tests=tests,
            query_type="general", sub_query_count=1, runtime={"model": "test"},
        )
        comparison = compare_capsules(left, right)
        self.assertFalse(comparison["same_answer_hash"])
        self.assertEqual(comparison["citation_jaccard"], 0.0)

    def test_sqlite_store_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            portable = store._SQLiteStore(Path(tmp) / "audit.db")
            portable.create_session("s1", "test")
            tests = run_claim_unit_tests(self.explanation)
            capsule = build_capsule(
                session_id="s1", query="q", answer="a", citations=[],
                explanation=self.explanation, claim_tests=tests,
                query_type="general", sub_query_count=1, runtime={},
            )
            portable.save_capsule(capsule)
            self.assertEqual(portable.get_capsule(capsule["capsule_id"])["answer"], "a")
            self.assertEqual(len(portable.list_capsules("s1")), 1)


if __name__ == "__main__":
    unittest.main()
