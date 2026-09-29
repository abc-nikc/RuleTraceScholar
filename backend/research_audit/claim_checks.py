"""Conservative deterministic checks for generated scientific claims.

These checks intentionally emit ``warning`` or ``untestable`` when a semantic
judgement would be required. They are guardrails, not a truth classifier.
"""

from __future__ import annotations

import re
from typing import Any


NUMBER_RE = re.compile(r"(?<!\w)[+-]?(?:\d+(?:\.\d+)?|\.\d+)\s*%?")


def _normalize_number(value: str) -> str:
    return re.sub(r"\s+", "", value).lstrip("+")


def run_claim_unit_tests(explanation: dict[str, Any]) -> dict[str, Any]:
    """Run auditable structural and numeric checks over TRACE claims."""
    tests: list[dict[str, Any]] = []
    claims = explanation.get("claims", [])

    for claim in claims:
        if not claim.get("requires_evidence"):
            continue
        claim_id = claim.get("claim_id", "unknown")
        valid_refs = claim.get("valid_citation_refs", [])
        invalid_refs = claim.get("invalid_citation_refs", [])
        evidence = claim.get("evidence", [])

        tests.append({
            "test_id": f"{claim_id}:citation-resolution",
            "claim_id": claim_id,
            "name": "Citation resolution",
            "status": "pass" if valid_refs and not invalid_refs else "fail",
            "detail": (
                f"Resolved references: {valid_refs}."
                if valid_refs and not invalid_refs
                else f"Valid references: {valid_refs}; invalid references: {invalid_refs}."
            ),
        })

        numbers = sorted({_normalize_number(value) for value in NUMBER_RE.findall(claim.get("text", ""))})
        if not numbers:
            tests.append({
                "test_id": f"{claim_id}:numeric-evidence",
                "claim_id": claim_id,
                "name": "Numeric evidence",
                "status": "untestable",
                "detail": "The claim contains no explicit numeric value.",
            })
            continue

        evidence_text = " ".join(str(item.get("excerpt", "")) for item in evidence)
        evidence_numbers = {_normalize_number(value) for value in NUMBER_RE.findall(evidence_text)}
        matched = [value for value in numbers if value in evidence_numbers]
        missing = [value for value in numbers if value not in evidence_numbers]
        tests.append({
            "test_id": f"{claim_id}:numeric-evidence",
            "claim_id": claim_id,
            "name": "Numeric evidence",
            "status": "pass" if not missing else "warning",
            "detail": (
                f"All claim values occur in cited excerpts: {matched}."
                if not missing
                else f"Values not found verbatim in cited excerpts: {missing}; manual or arithmetic verification is required."
            ),
            "matched_values": matched,
            "unmatched_values": missing,
        })

    counts = {status: 0 for status in ("pass", "warning", "fail", "untestable")}
    for item in tests:
        counts[item["status"]] += 1
    decision = "fail" if counts["fail"] else "review" if counts["warning"] else "pass"
    return {
        "schema_version": "1.0",
        "method": "deterministic scientific claim unit tests",
        "decision": decision,
        "counts": counts,
        "tests": tests,
        "limitations": [
            "Verbatim numeric matching does not validate statistical significance or causal interpretation.",
            "Warnings require review; they are not proof that a claim is false.",
        ],
    }
