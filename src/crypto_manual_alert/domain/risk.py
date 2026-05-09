from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    passed: bool
    severity: str
    message: str
    blocking: bool
    evidence_refs: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "blocking": self.blocking,
            "evidence_refs": list(self.evidence_refs),
            "details": self.details,
        }


@dataclass(frozen=True)
class RiskVerdict:
    allowed: bool
    reasons: list[str]
    warnings: list[str] = field(default_factory=list)
    rule_hits: list[RuleHit] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "rule_hits": [hit.to_public_dict() for hit in self.rule_hits],
        }
