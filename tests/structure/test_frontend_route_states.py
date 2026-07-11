from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_APP = ROOT / "frontend" / "src" / "app"
PLAYWRIGHT_CONFIG = ROOT / "frontend" / "playwright.config.ts"
NOTIFICATION_HISTORY = FRONTEND_APP / "runs" / "[traceId]" / "notification-history.tsx"
CONFIG_PAGE = FRONTEND_APP / "config" / "page.tsx"
SYSTEM_SCHEMA = ROOT / "frontend" / "src" / "lib" / "schemas" / "system.ts"


def test_frontend_declares_product_route_state_boundaries():
    for filename in ("loading.tsx", "error.tsx", "not-found.tsx"):
        path = FRONTEND_APP / filename
        assert path.exists(), f"{filename} must productize slow, broken, or missing routes"


def test_frontend_route_state_copy_stays_product_facing():
    forbidden = (
        "trace_id",
        "Parsed Plan",
        "request_json",
        "response_json",
        "Stack trace",
        "Unhandled Runtime Error",
        "404 | This page could not be found",
    )

    for filename in ("loading.tsx", "error.tsx", "not-found.tsx"):
        text = (FRONTEND_APP / filename).read_text(encoding="utf-8")
        assert "人工提醒" in text or "提醒工作台" in text
        assert all(token not in text for token in forbidden)


def test_playwright_webserver_uses_single_production_build_owner():
    text = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")

    assert "start_local_stack.py --frontend-mode production" in text
    assert "npm --prefix frontend run build" not in text


def test_notification_history_empty_latest_status_copy_is_consistent():
    text = NOTIFICATION_HISTORY.read_text(encoding="utf-8")

    assert "最新状态：Bark 已发送" in text
    assert "最新状态：发送失败" in text
    assert "发送明细待同步" in text
    assert 'return "通知记录待同步";' not in text


def test_config_readiness_schema_exposes_production_main_path_gate():
    text = SYSTEM_SCHEMA.read_text(encoding="utf-8")

    assert "candidate_sidecar_disabled: z.boolean().default(false)" in text
    assert "production_main_path_ready: z.boolean().default(false)" in text
    assert "main_path_blockers: z.array(z.string()).default([])" in text


def test_config_page_surfaces_production_main_path_readiness():
    text = CONFIG_PAGE.read_text(encoding="utf-8")

    assert 'label: "运行主链"' in text
    assert "production_main_path_ready" in text
    assert "mainPathBlockerText" in text
    assert "主链未就绪" in text
    assert 'mainPathReady ? "ready" : "main_path_blocked"' in text
    assert "需恢复默认主链" in text
    assert "detail: mainPathNote(readiness)" in text
    assert "最终生成路径需要保持默认稳定路径。" in text
