"""Dataset-agnostic evaluation helpers for the TRACE explanation layer."""

from __future__ import annotations

from collections import Counter
from typing import Any

from explainability import EvidenceRuleEngine


def evaluate_explanations(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate structural evidence metrics over answer/citation cases."""
    engine = EvidenceRuleEngine()
    reports = [
        engine.evaluate(
            case.get("answer", ""),
            case.get("citations", []),
            query_type=case.get("query_type", "general"),
            sub_query_count=case.get("sub_query_count", 1),
        )
        for case in cases
    ]
    if not reports:
        return {
            "num_cases": 0,
            "mean_reliability": 0.0,
            "decision_counts": {},
            "mean_metrics": {},
            "rule_pass_rates": {},
            "reports": [],
        }

    metric_names = list(reports[0]["metrics"])
    rule_ids = [rule["rule_id"] for rule in reports[0]["rule_trace"]]
    return {
        "num_cases": len(reports),
        "mean_reliability": _mean([report["reliability_score"] for report in reports]),
        "decision_counts": dict(Counter(report["decision"] for report in reports)),
        "mean_metrics": {
            name: _mean([report["metrics"][name] for report in reports])
            for name in metric_names
        },
        "rule_pass_rates": {
            rule_id: _mean([
                float(next(rule["passed"] for rule in report["rule_trace"] if rule["rule_id"] == rule_id))
                for report in reports
            ])
            for rule_id in rule_ids
        },
        "reports": reports,
    }


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0
