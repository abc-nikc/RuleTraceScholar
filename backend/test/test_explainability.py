"""Unit tests for the deterministic TRACE explainability layer."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from explainability.engine import EvidenceRuleEngine, logistic_relevance


def _citations():
    return [
        {
            "paper_id": "paper-a",
            "section": "3 Results",
            "page": 5,
            "chunk_id": "a-1",
            "node_type": "table",
            "evidence_excerpt": "Method A reaches 91.2 percent accuracy.",
            "retrieval_relevance": 0.91,
        },
        {
            "paper_id": "paper-b",
            "section": "4 Discussion",
            "page": 8,
            "chunk_id": "b-2",
            "node_type": "paragraph",
            "evidence_excerpt": "The gain is attributed to a retrieval diversity mechanism.",
            "retrieval_relevance": 0.83,
        },
    ]


class EvidenceRuleEngineTests(unittest.TestCase):
    def test_builds_claim_evidence_graph_and_passes_valid_references(self):
        report = EvidenceRuleEngine().evaluate(
            "Method A reaches 91.2% accuracy [1]. The gain uses diverse retrieval [2].",
            _citations(),
            query_type="experimental_result",
            sub_query_count=2,
        )

        self.assertEqual(report["metrics"]["citation_coverage"], 1.0)
        self.assertEqual(report["metrics"]["citation_validity"], 1.0)
        self.assertEqual(len(report["evidence_graph"]["edges"]), 2)
        self.assertEqual(report["calibration"]["status"], "uncalibrated")

    def test_flags_invalid_and_missing_citations_with_counterfactuals(self):
        report = EvidenceRuleEngine().evaluate(
            "Method A reaches 91.2% accuracy [9]. It also improves robustness.",
            _citations()[:1],
            query_type="experimental_result",
        )

        self.assertEqual(report["metrics"]["citation_validity"], 0.0)
        self.assertEqual(report["decision"], "insufficient")
        failed = {rule["rule_id"] for rule in report["rule_trace"] if not rule["passed"]}
        self.assertTrue({"R1", "R2"}.issubset(failed))
        self.assertTrue(any(item["target_rule"] == "R2" for item in report["counterfactuals"]))

    def test_thresholds_adapt_to_query_type_and_complexity(self):
        engine = EvidenceRuleEngine()
        background = engine.evaluate(
            "This is established background [1].", _citations()[:1], query_type="background"
        )
        experiment = engine.evaluate(
            "This is an experimental result [1].",
            _citations()[:1],
            query_type="experimental_result",
            sub_query_count=4,
        )

        self.assertGreater(
            experiment["thresholds"]["citation_coverage"],
            background["thresholds"]["citation_coverage"],
        )
        self.assertGreater(
            experiment["thresholds"]["release_score"],
            background["thresholds"]["release_score"],
        )

    def test_logistic_relevance_is_bounded(self):
        self.assertEqual(logistic_relevance(0), 0.5)
        self.assertTrue(0.99 < logistic_relevance(10) <= 1.0)
        self.assertIsNone(logistic_relevance("bad"))


if __name__ == "__main__":
    unittest.main()
