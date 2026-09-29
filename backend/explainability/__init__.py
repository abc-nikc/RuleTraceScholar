"""Process-faithful explainability for RuleTrace Scholar."""

from .engine import EvidenceRuleEngine
from .repair import repair_answer_with_evidence

__all__ = ["EvidenceRuleEngine", "repair_answer_with_evidence"]
