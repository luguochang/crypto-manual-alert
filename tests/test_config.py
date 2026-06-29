import os

import pytest

from jiami_crypto_alert.config import ConfigError, load_config


def test_default_config_disables_auto_ordering():
    config = load_config("config/default.yaml")

    assert config.trading.auto_order_enabled is False
    assert config.trading.manual_execution_required is True
    assert config.notification.bark_device_key_env == "BARK_DEVICE_KEY"


def test_prod_config_uses_real_public_market_data_provider():
    config = load_config("config/default.yaml", "config/prod.yaml")

    assert config.market_data.provider == "okx_public"


def test_config_rejects_auto_ordering(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
app:
  mode: MANUAL_ALERT
trading:
  auto_order_enabled: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="auto_order_enabled"):
        load_config(path)


def test_config_rejects_command_decision_engine(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
decision:
  engine: command
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="command"):
        load_config(path)


def test_config_rejects_forbidden_trade_key_env(monkeypatch):
    monkeypatch.setenv("OKX_TRADE_API_KEY", "not-allowed")

    with pytest.raises(ConfigError, match="forbidden"):
        load_config("config/default.yaml")


def test_secret_redaction(monkeypatch):
    monkeypatch.setenv("BARK_DEVICE_KEY", "secret-bark-key")
    config = load_config("config/default.yaml")

    rendered = str(config.safe_dict())

    assert "secret-bark-key" not in rendered
    assert "BARK_DEVICE_KEY" in rendered


def test_research_env_overrides(monkeypatch):
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("RESEARCH_SEARCH_PROVIDER", "responses_web_search")
    monkeypatch.setenv("RESEARCH_PLANNER", "llm")
    monkeypatch.setenv("RESEARCH_LEADER_MODE", "llm")
    monkeypatch.setenv("RESEARCH_MAX_QUERIES", "2")
    monkeypatch.setenv("RESEARCH_MAX_WORKERS", "2")
    monkeypatch.setenv("RESEARCH_REQUEST_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("SCHEDULER_JOB_TIMEOUT_SECONDS", "1800")

    config = load_config("config/default.yaml")

    assert config.research.enabled is True
    assert config.research.search_provider == "responses_web_search"
    assert config.research.planner == "llm"
    assert config.research.leader_mode == "llm"
    assert config.research.max_queries == 2
    assert config.research.max_workers == 2
    assert config.research.request_timeout_seconds == 5
    assert config.scheduler.job_timeout_seconds == 1800


def test_config_accepts_llm_research_planner_and_leader_mode(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text(
        """
research:
  planner: llm
  leader_mode: llm
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.research.planner == "llm"
    assert config.research.leader_mode == "llm"


def test_config_rejects_unknown_research_planner(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
research:
  planner: magic
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="research.planner"):
        load_config(path)


def test_config_rejects_unknown_research_leader_mode(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
research:
  leader_mode: magic
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="research.leader_mode"):
        load_config(path)
