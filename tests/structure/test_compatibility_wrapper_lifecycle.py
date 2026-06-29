from __future__ import annotations

from pathlib import Path


LIFECYCLE_DOC = Path("docs/formal/33-compatibility-wrapper-lifecycle.md")
MAIN_PLAN = Path("docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md")
MIGRATION_NOTE = Path("docs/migration/2026-07-03-checkpoint-8-legacy-convergence.md")

REQUIRED_WRAPPER_ROWS = {
    "src/crypto_manual_alert/agent_swarm/contracts.py": "src/crypto_manual_alert/orchestration/contracts.py",
    "src/crypto_manual_alert/agent_swarm/harness.py": "src/crypto_manual_alert/orchestration/harness.py",
    "src/crypto_manual_alert/agent_swarm/default_lead_plan.py": "src/crypto_manual_alert/lead/default_plan.py",
    "src/crypto_manual_alert/agent_swarm/shadow_orchestration.py": "src/crypto_manual_alert/orchestration/shadow_audit.py",
    "src/crypto_manual_alert/agent_swarm/shadow_failure.py": "src/crypto_manual_alert/orchestration/shadow_failure.py",
    "src/crypto_manual_alert/agent_swarm/workers.py": "src/crypto_manual_alert/market_agents/",
    "src/crypto_manual_alert/agent_swarm/local_workers/": "src/crypto_manual_alert/market_agents/",
    "src/crypto_manual_alert/skills/runtime.py": "src/crypto_manual_alert/skills/context_loader.py",
}


def test_compatibility_wrapper_lifecycle_table_covers_current_wrappers():
    source = LIFECYCLE_DOC.read_text(encoding="utf-8")

    required_columns = {
        "Compatibility wrapper",
        "Canonical owner",
        "Allowed usage",
        "No-new-logic rule",
        "Removal condition",
        "Current guard",
    }
    for column in required_columns:
        assert column in source

    for wrapper, canonical_owner in REQUIRED_WRAPPER_ROWS.items():
        row = _markdown_row_containing(source, wrapper)
        assert canonical_owner in row
        assert "compatibility import" in row
        assert "no new logic" in row
        assert "structure test" in row


def test_main_plan_and_migration_note_reference_wrapper_lifecycle_table():
    lifecycle_doc_ref = "33-compatibility-wrapper-lifecycle.md"
    assert lifecycle_doc_ref in MAIN_PLAN.read_text(encoding="utf-8")
    assert lifecycle_doc_ref in MIGRATION_NOTE.read_text(encoding="utf-8")


def test_lifecycle_table_records_secondary_owners_and_non_removable_package_facades():
    source = LIFECYCLE_DOC.read_text(encoding="utf-8")

    shadow_orchestration_row = _markdown_row_containing(
        source,
        "src/crypto_manual_alert/agent_swarm/shadow_orchestration.py",
    )
    assert "src/crypto_manual_alert/orchestration/shadow_failure.py" in shadow_orchestration_row

    non_wrapper_section = source.split("## Non-Wrappers Kept In Place", maxsplit=1)[1]
    assert "src/crypto_manual_alert/agent_swarm/__init__.py" in non_wrapper_section
    assert "src/crypto_manual_alert/skills/__init__.py" in non_wrapper_section
    assert "stable package API facade" in non_wrapper_section


def _markdown_row_containing(source: str, needle: str) -> str:
    rows = [
        line
        for line in source.splitlines()
        if line.startswith("|") and needle in line
    ]
    assert len(rows) == 1, f"Expected one lifecycle row for {needle}, found {len(rows)}"
    return rows[0]
