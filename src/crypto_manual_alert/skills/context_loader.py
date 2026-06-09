from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from crypto_manual_alert.config import Config
from crypto_manual_alert.domain import MarketSnapshot


REQUIRED_REFERENCES = (
    "data-sources.md",
    "event-pool.md",
    "exchange-derivatives.md",
    "templates.md",
)
EXPECTED_SKILL_NAME = "crypto-macro-decision"


@dataclass(frozen=True)
class SkillInfo:
    path: Path
    sha256: str
    name: str


@dataclass(frozen=True)
class SkillContext:
    path: Path
    sha256: str
    name: str
    skill_md: str
    references: dict[str, str]
    okx_snapshot_script: Path

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "sha256": self.sha256,
            "required_references": list(self.references),
            "okx_snapshot_script": str(self.okx_snapshot_script),
            "references": self.references,
        }


class SkillRuntime:
    def __init__(self, config: Config):
        self.config = config
        self.path = Path(config.decision.skill_path)

    def info(self) -> SkillInfo:
        skill_file = self.path / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"Skill file not found: {skill_file}")
        content = skill_file.read_bytes()
        return SkillInfo(path=self.path, sha256=hashlib.sha256(content).hexdigest(), name=EXPECTED_SKILL_NAME)

    def load_context(self) -> SkillContext:
        skill_file = self.path / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"Skill file not found: {skill_file}")
        skill_md = skill_file.read_text(encoding="utf-8")
        name = _skill_name(skill_md)
        if name != EXPECTED_SKILL_NAME:
            raise ValueError(f"Skill name must be {EXPECTED_SKILL_NAME}, got {name or '<missing>'}")

        references: dict[str, str] = {}
        for name in REQUIRED_REFERENCES:
            reference_file = self.path / "references" / name
            if not reference_file.exists():
                raise FileNotFoundError(f"Required skill reference not found: {reference_file}")
            references[name] = reference_file.read_text(encoding="utf-8")

        okx_snapshot_script = self.path / "scripts" / "okx_snapshot.py"
        if not okx_snapshot_script.exists():
            raise FileNotFoundError(f"Required skill script not found: {okx_snapshot_script}")

        digest = hashlib.sha256()
        digest.update(skill_file.read_bytes())
        for name in REQUIRED_REFERENCES:
            digest.update(name.encode("utf-8"))
            digest.update(references[name].encode("utf-8"))
        digest.update(okx_snapshot_script.read_bytes())

        return SkillContext(
            path=self.path,
            sha256=digest.hexdigest(),
            name=EXPECTED_SKILL_NAME,
            skill_md=skill_md,
            references=references,
            okx_snapshot_script=okx_snapshot_script,
        )

    def build_prompt_packet(self, snapshot: MarketSnapshot, context: SkillContext | None = None) -> dict[str, object]:
        from crypto_manual_alert.skills.prompt_context import compact_prompt_context

        context = context or self.load_context()
        return {
            "skill": {
                "name": context.name,
                "path": str(context.path),
                "sha256": context.sha256,
                "required_references": list(context.references),
                "okx_snapshot_script": str(context.okx_snapshot_script),
            },
            "boundary": "manual-alert-only; do not place orders; user must manually operate in OKX",
            "required_output": "strict JSON DecisionPlan",
            "skill_context": compact_prompt_context(context),
            "market_snapshot": snapshot.to_public_dict(),
        }


def _skill_name(skill_md: str) -> str | None:
    for line in skill_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            return stripped.split(":", 1)[1].strip().strip("\"'")
    return None
