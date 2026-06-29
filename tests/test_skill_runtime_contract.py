from pathlib import Path

import pytest

from jiami_crypto_alert.config import load_config
from jiami_crypto_alert.market_data import FixtureMarketDataProvider
from jiami_crypto_alert.skill_runtime import SkillRuntime


def test_skill_runtime_loads_required_context():
    config = load_config("config/default.yaml")

    context = SkillRuntime(config).load_context()

    assert context.name == "crypto-macro-decision"
    assert context.sha256
    assert "data-sources.md" in context.references
    assert "exchange-derivatives.md" in context.references
    assert "templates.md" in context.references
    assert context.okx_snapshot_script.name == "okx_snapshot.py"


def test_skill_runtime_builds_compact_prompt_context():
    config = load_config("config/default.yaml")
    snapshot = FixtureMarketDataProvider().fetch_snapshot("ETH-USDT-SWAP")

    packet = SkillRuntime(config).build_prompt_packet(snapshot)

    assert packet["skill_context"]["mode"] == "compact"
    assert packet["skill_context"]["skill_md_excerpt"]
    assert len(packet["skill_context"]["skill_md_excerpt"]) <= 12050
    assert set(packet["skill_context"]["reference_excerpts"]) == {"data-sources.md", "exchange-derivatives.md", "templates.md"}
    assert all(len(text) <= 2550 for text in packet["skill_context"]["reference_excerpts"].values())
    assert packet["skill"]["sha256"]


def test_skill_runtime_blocks_when_required_reference_missing(tmp_path):
    skill_dir = tmp_path / "skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: crypto-macro-decision\n---\n", encoding="utf-8")
    (skill_dir / "references" / "data-sources.md").write_text("data", encoding="utf-8")
    (skill_dir / "references" / "templates.md").write_text("templates", encoding="utf-8")
    (skill_dir / "scripts" / "okx_snapshot.py").write_text("print('{}')", encoding="utf-8")
    config = load_config("config/default.yaml")
    config = _replace_skill_path(config, skill_dir)

    with pytest.raises(FileNotFoundError, match="exchange-derivatives.md"):
        SkillRuntime(config).load_context()


def test_skill_runtime_blocks_when_okx_snapshot_script_missing(tmp_path):
    skill_dir = tmp_path / "skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: crypto-macro-decision\n---\n", encoding="utf-8")
    (skill_dir / "references" / "data-sources.md").write_text("data", encoding="utf-8")
    (skill_dir / "references" / "exchange-derivatives.md").write_text("derivatives", encoding="utf-8")
    (skill_dir / "references" / "templates.md").write_text("templates", encoding="utf-8")
    config = load_config("config/default.yaml")
    config = _replace_skill_path(config, skill_dir)

    with pytest.raises(FileNotFoundError, match="okx_snapshot.py"):
        SkillRuntime(config).load_context()


def test_skill_runtime_rejects_wrong_skill_name(tmp_path):
    skill_dir = tmp_path / "skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: other-skill\n---\n", encoding="utf-8")
    (skill_dir / "references" / "data-sources.md").write_text("data", encoding="utf-8")
    (skill_dir / "references" / "exchange-derivatives.md").write_text("derivatives", encoding="utf-8")
    (skill_dir / "references" / "templates.md").write_text("templates", encoding="utf-8")
    (skill_dir / "scripts" / "okx_snapshot.py").write_text("print('{}')", encoding="utf-8")
    config = load_config("config/default.yaml")
    config = _replace_skill_path(config, skill_dir)

    with pytest.raises(ValueError, match="crypto-macro-decision"):
        SkillRuntime(config).load_context()


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
