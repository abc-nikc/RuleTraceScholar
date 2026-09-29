"""Claim-to-evidence tracing and transparent reliability rules.

The engine is deliberately deterministic.  It does not ask an LLM to explain
another LLM.  Instead, it inspects the answer citations and the same retrieval
metadata used during generation, then exports every proposition and rule that
contributed to the reliability result.

The resulting reliability score is an *uncalibrated evidence-quality index*,
not a probability that an answer is true.  A calibration hook is kept in the
report so future benchmark-based calibration can be added without changing the
public response schema.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable


CITATION_RE = re.compile(r"(?<!\!)\[(\d+)\](?!\()")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?。！？；;])\s+|\n+")
MARKDOWN_PREFIX_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s+|>\s*)")


@dataclass(frozen=True)
class RuleThresholds:
    citation_coverage: float
    citation_validity: float
    traceability: float
    source_diversity: float
    evidence_density: float
    release_score: float


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    name: str
    expression: str
    value: float
    threshold: float
    passed: bool
    weight: float
    rationale: str


class EvidenceRuleEngine:
    """Build a claim-evidence graph and evaluate adaptive evidence rules."""

    QUERY_THRESHOLDS: dict[str, RuleThresholds] = {
        "experimental_result": RuleThresholds(0.90, 1.00, 0.85, 0.55, 0.65, 0.78),
        "method": RuleThresholds(0.82, 1.00, 0.80, 0.45, 0.55, 0.72),
        "background": RuleThresholds(0.75, 0.98, 0.75, 0.45, 0.45, 0.68),
        "general": RuleThresholds(0.80, 0.98, 0.78, 0.45, 0.50, 0.70),
    }

    RULE_WEIGHTS = {
        "R1": 0.34,
        "R2": 0.20,
        "R3": 0.20,
        "R4": 0.14,
        "R5": 0.12,
    }

    def __init__(self, excerpt_chars: int = 280):
        self.excerpt_chars = excerpt_chars

    def evaluate(
        self,
        answer: str,
        citations: list[dict[str, Any]],
        *,
        query_type: str = "general",
        sub_query_count: int = 1,
    ) -> dict[str, Any]:
        """Return a JSON-serializable explanation report."""
        query_type = query_type if query_type in self.QUERY_THRESHOLDS else "general"
        thresholds = self._adapt_thresholds(query_type, sub_query_count)
        claims = self._extract_claims(answer, citations)

        factual_claims = [claim for claim in claims if claim["requires_evidence"]]
        cited_claims = [claim for claim in factual_claims if claim["valid_citation_refs"]]
        all_refs = [ref for claim in factual_claims for ref in claim["citation_refs"]]
        valid_refs = [ref for claim in factual_claims for ref in claim["valid_citation_refs"]]

        coverage = self._ratio(len(cited_claims), len(factual_claims))
        validity = self._ratio(len(valid_refs), len(all_refs))
        traceability = self._traceability(citations, valid_refs)
        diversity = self._source_diversity(citations, valid_refs, sub_query_count)
        density = self._evidence_density(valid_refs, factual_claims)

        rules = [
            self._rule(
                "R1", "Claim grounding", "cited factual claims / factual claims",
                coverage, thresholds.citation_coverage,
                f"{len(cited_claims)} of {len(factual_claims)} factual claims have a valid citation.",
            ),
            self._rule(
                "R2", "Citation validity", "valid citation references / all citation references",
                validity, thresholds.citation_validity,
                f"{len(valid_refs)} of {len(all_refs)} citation references resolve to retrieved evidence.",
            ),
            self._rule(
                "R3", "Source traceability", "sources with paper and location metadata / cited sources",
                traceability, thresholds.traceability,
                "Traceable evidence identifies a paper and at least one location field.",
            ),
            self._rule(
                "R4", "Evidence diversity", "observed source diversity / expected diversity",
                diversity, thresholds.source_diversity,
                "Diversity rewards independent papers and sections instead of repeated nearby chunks.",
            ),
            self._rule(
                "R5", "Evidence density", "mean valid sources per factual claim, capped at two",
                density, thresholds.evidence_density,
                "Dense support matters more for multi-part and quantitative answers.",
            ),
        ]

        metric_values = {
            "R1": coverage,
            "R2": validity,
            "R3": traceability,
            "R4": diversity,
            "R5": density,
        }
        raw_score = sum(self.RULE_WEIGHTS[key] * metric_values[key] for key in self.RULE_WEIGHTS)
        # A small explicit penalty prevents a high average from hiding a failed
        # hard rule.  It is deterministic and appears in the exported trace.
        hard_rule_factor = 0.85 + 0.15 * self._ratio(sum(r.passed for r in rules), len(rules))
        reliability = round(max(0.0, min(1.0, raw_score * hard_rule_factor)), 4)
        uncertainty = round(1.0 - reliability, 4)

        margin = reliability - thresholds.release_score
        if margin >= 0:
            decision = "supported"
        elif margin >= -0.18:
            decision = "caution"
        else:
            decision = "insufficient"

        counterfactuals = self._counterfactuals(rules, claims, citations)
        graph = self._build_graph(claims, citations)

        return {
            "schema_version": "1.0",
            "method": "TRACE adaptive evidence rules",
            "query_type": query_type,
            "decision": decision,
            "reliability_score": reliability,
            "reliability_percent": round(reliability * 100),
            "uncertainty_index": uncertainty,
            "calibration": {
                "status": "uncalibrated",
                "meaning": "Evidence-quality index; not a probability that the answer is true.",
            },
            "metrics": {
                "citation_coverage": round(coverage, 4),
                "citation_validity": round(validity, 4),
                "traceability": round(traceability, 4),
                "source_diversity": round(diversity, 4),
                "evidence_density": round(density, 4),
            },
            "thresholds": asdict(thresholds),
            "rule_trace": [asdict(rule) for rule in rules],
            "claims": claims,
            "evidence_graph": graph,
            "counterfactuals": counterfactuals,
            "limitations": [
                "The report measures citation structure and provenance, not semantic truth or causality.",
                "Reliability thresholds are transparent heuristics until calibrated on a labelled benchmark.",
                "A cited passage can still be misinterpreted; semantic entailment evaluation remains a separate task.",
            ],
        }

    def _adapt_thresholds(self, query_type: str, sub_query_count: int) -> RuleThresholds:
        base = self.QUERY_THRESHOLDS[query_type]
        complexity_bonus = min(max(sub_query_count - 1, 0) * 0.02, 0.08)
        return RuleThresholds(
            citation_coverage=min(0.98, base.citation_coverage + complexity_bonus),
            citation_validity=base.citation_validity,
            traceability=min(0.95, base.traceability + complexity_bonus / 2),
            source_diversity=min(0.80, base.source_diversity + complexity_bonus),
            evidence_density=min(0.85, base.evidence_density + complexity_bonus / 2),
            release_score=min(0.88, base.release_score + complexity_bonus / 2),
        )

    def _extract_claims(self, answer: str, citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        text = re.sub(r"```.*?```", " ", answer or "", flags=re.DOTALL)
        pieces = []
        for raw in SENTENCE_BOUNDARY_RE.split(text):
            cleaned = MARKDOWN_PREFIX_RE.sub("", raw).strip()
            if cleaned:
                pieces.append(cleaned)

        claims = []
        for index, piece in enumerate(pieces, 1):
            refs = [int(value) for value in CITATION_RE.findall(piece)]
            valid_refs = sorted({ref for ref in refs if 1 <= ref <= len(citations)})
            invalid_refs = sorted({ref for ref in refs if ref < 1 or ref > len(citations)})
            clean_text = re.sub(CITATION_RE, "", piece).strip()
            requires_evidence = self._requires_evidence(clean_text)
            evidence = [self._evidence_summary(citations[ref - 1], ref) for ref in valid_refs]
            claims.append({
                "claim_id": f"C{index}",
                "text": clean_text,
                "claim_type": self._claim_type(clean_text),
                "requires_evidence": requires_evidence,
                "citation_refs": refs,
                "valid_citation_refs": valid_refs,
                "invalid_citation_refs": invalid_refs,
                "grounded": bool(valid_refs) if requires_evidence else True,
                "evidence": evidence,
            })
        return claims

    @staticmethod
    def _requires_evidence(text: str) -> bool:
        if len(text) < 12 or text.endswith(":"):
            return False
        lowered = text.lower()
        non_claim_markers = (
            "provided context does not contain", "no relevant information found",
            "cannot be determined", "信息不足", "无法确定", "无法回答",
        )
        return not any(marker in lowered for marker in non_claim_markers)

    @staticmethod
    def _claim_type(text: str) -> str:
        lowered = text.lower()
        if re.search(r"\b\d+(?:\.\d+)?%?\b", text) or any(
            token in lowered for token in ("accuracy", "rmse", "result", "benchmark", "结果", "指标")
        ):
            return "experimental_result"
        if any(token in lowered for token in ("because", "therefore", "causes", "导致", "因此", "由于")):
            return "causal_or_inferential"
        if any(token in lowered for token in ("method", "model", "algorithm", "pipeline", "方法", "模型", "流程")):
            return "method"
        return "factual"

    def _evidence_summary(self, citation: dict[str, Any], ref: int) -> dict[str, Any]:
        excerpt = str(citation.get("evidence_excerpt") or citation.get("text") or "")
        excerpt = re.sub(r"\s+", " ", excerpt).strip()[: self.excerpt_chars]
        return {
            "ref": ref,
            "paper_id": citation.get("paper_id", ""),
            "section": citation.get("section", ""),
            "page": citation.get("page", ""),
            "chunk_id": citation.get("chunk_id", ""),
            "node_type": citation.get("node_type", ""),
            "retrieval_relevance": citation.get("retrieval_relevance"),
            "excerpt": excerpt,
        }

    def _traceability(self, citations: list[dict[str, Any]], refs: Iterable[int]) -> float:
        unique_refs = sorted(set(refs))
        if not unique_refs:
            return 0.0
        traceable = 0
        for ref in unique_refs:
            citation = citations[ref - 1]
            has_source = bool(citation.get("paper_id"))
            has_location = bool(citation.get("section") or citation.get("page") or citation.get("chunk_id"))
            traceable += int(has_source and has_location)
        return self._ratio(traceable, len(unique_refs))

    def _source_diversity(
        self,
        citations: list[dict[str, Any]],
        refs: Iterable[int],
        sub_query_count: int,
    ) -> float:
        unique_refs = sorted(set(refs))
        if not unique_refs:
            return 0.0
        sources = set()
        sections = set()
        for ref in unique_refs:
            citation = citations[ref - 1]
            paper = citation.get("paper_id") or "unknown"
            section = citation.get("section") or citation.get("page") or "unknown"
            sources.add(paper)
            sections.add((paper, str(section)))
        expected = min(max(1, sub_query_count), 3)
        paper_component = min(len(sources) / expected, 1.0)
        section_component = min(len(sections) / max(expected + 1, 2), 1.0)
        return 0.7 * paper_component + 0.3 * section_component

    @staticmethod
    def _evidence_density(valid_refs: list[int], claims: list[dict[str, Any]]) -> float:
        if not claims:
            return 0.0
        mean_sources = len(valid_refs) / len(claims)
        return min(mean_sources / 2.0, 1.0)

    def _rule(
        self,
        rule_id: str,
        name: str,
        expression: str,
        value: float,
        threshold: float,
        rationale: str,
    ) -> RuleResult:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            expression=expression,
            value=round(value, 4),
            threshold=round(threshold, 4),
            passed=value + 1e-9 >= threshold,
            weight=self.RULE_WEIGHTS[rule_id],
            rationale=rationale,
        )

    @staticmethod
    def _counterfactuals(
        rules: list[RuleResult],
        claims: list[dict[str, Any]],
        citations: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        actions = []
        failed = {rule.rule_id for rule in rules if not rule.passed}
        unsupported = [claim["claim_id"] for claim in claims if claim["requires_evidence"] and not claim["grounded"]]
        if "R1" in failed:
            actions.append({
                "target_rule": "R1",
                "action": f"Retrieve or remove support for uncited claims: {', '.join(unsupported[:6]) or 'none identified'}.",
            })
        if "R2" in failed:
            actions.append({"target_rule": "R2", "action": "Regenerate citation indices so every reference resolves to an evidence node."})
        if "R3" in failed:
            actions.append({"target_rule": "R3", "action": "Re-index sources with paper, section, page, and chunk provenance."})
        if "R4" in failed:
            actions.append({"target_rule": "R4", "action": "Retrieve evidence from another paper or independent section before synthesis."})
        if "R5" in failed:
            actions.append({"target_rule": "R5", "action": "Add a second supporting passage for quantitative or multi-part claims."})
        if not citations:
            actions.append({"target_rule": "evidence", "action": "Abstain or run retrieval again because no evidence was attached."})
        return actions

    def _build_graph(
        self,
        claims: list[dict[str, Any]],
        citations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        used_refs = sorted({ref for claim in claims for ref in claim["valid_citation_refs"]})
        evidence_nodes = [
            {"evidence_id": f"E{ref}", **self._evidence_summary(citations[ref - 1], ref)}
            for ref in used_refs
        ]
        edges = [
            {
                "from": claim["claim_id"],
                "to": f"E{ref}",
                "relation": "supported_by",
            }
            for claim in claims
            for ref in claim["valid_citation_refs"]
        ]
        return {
            "claim_nodes": [
                {
                    "claim_id": claim["claim_id"],
                    "text": claim["text"],
                    "grounded": claim["grounded"],
                    "claim_type": claim["claim_type"],
                }
                for claim in claims
                if claim["requires_evidence"]
            ],
            "evidence_nodes": evidence_nodes,
            "edges": edges,
        }

    @staticmethod
    def _ratio(numerator: int | float, denominator: int | float) -> float:
        return float(numerator) / float(denominator) if denominator else 0.0


def logistic_relevance(score: Any) -> float | None:
    """Map an arbitrary CrossEncoder logit to a stable 0..1 display value."""
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return None
    return round(1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, numeric)))), 4)
