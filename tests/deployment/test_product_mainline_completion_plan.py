from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "v2" / "22-agent-product-mainline-completion-plan.md"

EXPECTED_REQUIREMENT_IDS = {
    "PM-ENTRY-001",
    "PM-ENTRY-002",
    "PM-ENTRY-003",
    "PM-ENTRY-004",
    "PM-ENTRY-005",
    "PM-MON-001",
    "PM-MON-002",
    "PM-MON-003",
    "PM-MEM-001",
    "PM-MEM-002",
    "PM-MEM-003",
    "PM-OUT-001",
    "PM-OUT-002",
    "PM-OUT-003",
    "PM-EVAL-001",
    "PM-EVAL-002",
    "PM-EVAL-003",
    "PM-EVAL-004",
    "PM-EVAL-005",
    "PM-COM-001",
    "PM-COM-002",
    "PM-INT-001",
    "PM-INT-002",
    "PM-LIFE-001",
    "PM-PROD-001",
    "PM-PROD-002",
    "PM-PROD-003",
    "PM-PROD-004",
    "PM-PROD-005",
    "PM-PROD-006",
    "PM-NOTIFY-X01",
}


def _rows(source: str) -> list[tuple[str, str, str, str, str]]:
    return re.findall(
        r"(?m)^\| (PM-[A-Z]+-[A-Z0-9]+) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$",
        source,
    )


def test_mainline_plan_has_complete_unique_requirement_inventory() -> None:
    source = PLAN.read_text(encoding="utf-8")
    rows = _rows(source)
    ids = [row[0] for row in rows]

    assert len(ids) == len(set(ids))
    assert set(ids) == EXPECTED_REQUIREMENT_IDS
    assert all(all(cell.strip() for cell in row) for row in rows)


def test_mainline_plan_keeps_notification_excluded_without_shrinking_other_work() -> None:
    source = PLAN.read_text(encoding="utf-8")
    rows = {row[0]: row[1:] for row in _rows(source)}

    notification = " ".join(rows["PM-NOTIFY-X01"])
    assert "excluded" in notification.lower()
    assert "Bark/Web Push/Email" in notification
    assert all(
        "explicitly excluded by user" not in " ".join(cells).lower()
        for requirement_id, cells in rows.items()
        if requirement_id != "PM-NOTIFY-X01"
    )


def test_mainline_plan_preserves_framework_ownership_and_evidence_boundaries() -> None:
    source = PLAN.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    assert "Authority class: `informative execution control`" in source
    assert "Status: `V2: PARTIAL`" in source
    assert "Production Ready: `NO`" in source
    assert "No custom checkpoint store" in source
    assert "general Agent loop" in source
    assert "commercial runtime becomes mandatory" in source
    assert "A fixture can prove deterministic logic" in normalized
    assert "never closes a real-provider, restart or production row" in normalized
    assert "External notification delivery is explicitly out of scope" in source
