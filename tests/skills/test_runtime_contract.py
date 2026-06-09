from pathlib import Path
import sys

import pytest

import crypto_manual_alert.skills.context_loader as canonical_skill_runtime
from crypto_manual_alert.config import load_config
from crypto_manual_alert.market.providers import FixtureMarketDataProvider
from crypto_manual_alert.skills.context_loader import SkillRuntime as CanonicalSkillRuntime
from crypto_manual_alert.skills.runtime import SkillRuntime as RuntimeCompatibilitySkillRuntime


def test_skills_package_import_does_not_eagerly_import_runtime():
    previous_runtime = sys.modules.pop("crypto_manual_alert.skills.runtime", None)
    sys.modules.pop("crypto_manual_alert.skills", None)
    try:
        __import__("crypto_manual_alert.skills")

        assert "crypto_manual_alert.skills.runtime" not in sys.modules
    finally:
        sys.modules.pop("crypto_manual_alert.skills", None)
        if previous_runtime is not None:
            sys.modules["crypto_manual_alert.skills.runtime"] = previous_runtime


@pytest.mark.parametrize(
    "name",
    [
        "CommandDecisionEngine",
        "DecisionEngine",
        "FixtureDecisionEngine",
        "OpenAICompatibleDecisionEngine",
        "SkillContext",
        "SkillInfo",
        "SkillRuntime",
    ],
)
def test_skills_runtime_exports_declared_runtime_objects(name):
    import crypto_manual_alert.skills.runtime as compatibility_runtime

    assert getattr(compatibility_runtime, name)


def test_runtime_compatibility_exports_canonical_skill_runtime():
    assert RuntimeCompatibilitySkillRuntime is CanonicalSkillRuntime


def test_skill_runtime_loads_required_context():
    config = load_config("config/default.yaml")

    context = CanonicalSkillRuntime(config).load_context()

    assert context.name == "crypto-macro-decision"
    assert context.sha256
    assert "data-sources.md" in context.references
    assert "event-pool.md" in context.references
    assert "exchange-derivatives.md" in context.references
    assert "templates.md" in context.references
    assert context.okx_snapshot_script.name == "okx_snapshot.py"


def test_skill_runtime_builds_compact_prompt_context():
    config = load_config("config/default.yaml")
    snapshot = FixtureMarketDataProvider().fetch_snapshot("ETH-USDT-SWAP")

    packet = CanonicalSkillRuntime(config).build_prompt_packet(snapshot)

    assert packet["skill_context"]["mode"] == "compact"
    assert packet["skill_context"]["skill_md_excerpt"]
    assert len(packet["skill_context"]["skill_md_excerpt"]) <= 12050
    assert set(packet["skill_context"]["reference_excerpts"]) == {
        "data-sources.md",
        "event-pool.md",
        "exchange-derivatives.md",
        "templates.md",
    }
    assert all(len(text) <= 2550 for text in packet["skill_context"]["reference_excerpts"].values())
    assert packet["skill"]["sha256"]


def test_skill_runtime_blocks_when_required_reference_missing(tmp_path):
    skill_dir = tmp_path / "skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: crypto-macro-decision\n---\n", encoding="utf-8")
    (skill_dir / "references" / "data-sources.md").write_text("data", encoding="utf-8")
    (skill_dir / "references" / "event-pool.md").write_text("events", encoding="utf-8")
    (skill_dir / "references" / "templates.md").write_text("templates", encoding="utf-8")
    (skill_dir / "scripts" / "okx_snapshot.py").write_text("print('{}')", encoding="utf-8")
    config = load_config("config/default.yaml")
    config = _replace_skill_path(config, skill_dir)

    with pytest.raises(FileNotFoundError, match="exchange-derivatives.md"):
        CanonicalSkillRuntime(config).load_context()


def test_skill_runtime_hash_changes_when_event_pool_changes(tmp_path):
    skill_dir = tmp_path / "skill"
    references_dir = skill_dir / "references"
    scripts_dir = skill_dir / "scripts"
    references_dir.mkdir(parents=True)
    scripts_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: crypto-macro-decision\n---\n", encoding="utf-8")
    (references_dir / "data-sources.md").write_text("data", encoding="utf-8")
    (references_dir / "event-pool.md").write_text("events:first", encoding="utf-8")
    (references_dir / "exchange-derivatives.md").write_text("derivatives", encoding="utf-8")
    (references_dir / "templates.md").write_text("templates", encoding="utf-8")
    (scripts_dir / "okx_snapshot.py").write_text("print('{}')", encoding="utf-8")
    config = _replace_skill_path(load_config("config/default.yaml"), skill_dir)

    first_hash = CanonicalSkillRuntime(config).load_context().sha256
    (references_dir / "event-pool.md").write_text("events:changed", encoding="utf-8")
    second_hash = CanonicalSkillRuntime(config).load_context().sha256

    assert first_hash != second_hash


def test_skill_runtime_blocks_when_okx_snapshot_script_missing(tmp_path):
    skill_dir = tmp_path / "skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: crypto-macro-decision\n---\n", encoding="utf-8")
    (skill_dir / "references" / "data-sources.md").write_text("data", encoding="utf-8")
    (skill_dir / "references" / "event-pool.md").write_text("events", encoding="utf-8")
    (skill_dir / "references" / "exchange-derivatives.md").write_text("derivatives", encoding="utf-8")
    (skill_dir / "references" / "templates.md").write_text("templates", encoding="utf-8")
    config = load_config("config/default.yaml")
    config = _replace_skill_path(config, skill_dir)

    with pytest.raises(FileNotFoundError, match="okx_snapshot.py"):
        CanonicalSkillRuntime(config).load_context()


def test_skill_runtime_rejects_wrong_skill_name(tmp_path):
    skill_dir = tmp_path / "skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: other-skill\n---\n", encoding="utf-8")
    (skill_dir / "references" / "data-sources.md").write_text("data", encoding="utf-8")
    (skill_dir / "references" / "event-pool.md").write_text("events", encoding="utf-8")
    (skill_dir / "references" / "exchange-derivatives.md").write_text("derivatives", encoding="utf-8")
    (skill_dir / "references" / "templates.md").write_text("templates", encoding="utf-8")
    (skill_dir / "scripts" / "okx_snapshot.py").write_text("print('{}')", encoding="utf-8")
    config = load_config("config/default.yaml")
    config = _replace_skill_path(config, skill_dir)

    with pytest.raises(ValueError, match="crypto-macro-decision"):
        CanonicalSkillRuntime(config).load_context()


def _replace_skill_path(config, path: Path):
    decision = config.decision.__class__(**{**config.decision.__dict__, "skill_path": str(path)})
    return config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=decision,
        notification=config.notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
    )
