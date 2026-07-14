from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_APP = ROOT / "frontend" / "src" / "app"
PLAYWRIGHT_CONFIG = ROOT / "frontend" / "playwright.config.ts"
FRONTEND_FEATURES = ROOT / "frontend" / "src" / "features"
WORK_SURFACE = FRONTEND_FEATURES / "work" / "work-surface.tsx"
RUNS_SURFACE = FRONTEND_FEATURES / "runs" / "runs-surface.tsx"
ANALYSIS_PROJECTION = FRONTEND_FEATURES / "analysis" / "analysis-projection.tsx"
RESEARCH_EVIDENCE = FRONTEND_FEATURES / "analysis" / "research-evidence.tsx"
PRODUCT_API_SCHEMA = ROOT / "frontend" / "src" / "lib" / "schemas" / "product-api.ts"
OFFICIAL_FLOW_E2E = (
    ROOT / "frontend" / "tests" / "e2e-v2" / "official-stream-main-flow.spec.ts"
)
WORK_PRODUCT_E2E = ROOT / "frontend" / "tests" / "e2e-v2" / "work-product.spec.ts"


def test_frontend_declares_product_route_state_boundaries():
    required_contracts = {
        "loading.tsx": ("export default function Loading", 'role="status"'),
        "error.tsx": ("export default function GlobalError", 'role="alert"', "reset"),
        "not-found.tsx": ("export default function NotFound", 'href="/work"'),
    }

    for filename, required_texts in required_contracts.items():
        source = (FRONTEND_APP / filename).read_text(encoding="utf-8")
        assert all(required_text in source for required_text in required_texts), filename


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

    required_copy = {
        "loading.tsx": ("正在加载工作台",),
        "error.tsx": ("页面暂时无法加载", "当前工作区遇到错误，请重试。"),
        "not-found.tsx": ("没有找到这个页面", "返回当前可用的分析工作台。"),
    }

    for filename, required_texts in required_copy.items():
        text = (FRONTEND_APP / filename).read_text(encoding="utf-8")
        assert all(required_text in text for required_text in required_texts), filename
        assert all(token not in text for token in forbidden)


def test_playwright_covers_desktop_and_pixel7_and_allows_external_production_server():
    text = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")

    assert "process.env.PLAYWRIGHT_FRONTEND_BASE_URL" in text
    assert 'process.env.PLAYWRIGHT_EXTERNAL_SERVER === "1"' in text
    assert "webServer: externalServer" in text
    assert "? undefined" in text
    assert 'name: "fixture-desktop"' in text
    assert '...devices["Desktop Chrome"]' in text
    assert 'name: "fixture-pixel-7"' in text
    assert '...devices["Pixel 7"]' in text
    assert "start_local_stack.py --frontend-mode production" not in text


def test_product_surfaces_expose_user_facing_loading_error_and_empty_states():
    work = WORK_SURFACE.read_text(encoding="utf-8")
    runs = RUNS_SURFACE.read_text(encoding="utf-8")
    research = RESEARCH_EVIDENCE.read_text(encoding="utf-8")

    for required_text in (
        "请求未完成",
        "正在提交分析",
        "正在恢复分析",
        "等待新的分析请求",
    ):
        assert required_text in work
    for required_text in (
        "正在读取分析记录",
        "分析记录读取失败",
        "暂无分析记录",
        "重新读取",
    ):
        assert required_text in runs
    for required_text in (
        "证据收集中",
        "检索不可用",
        "暂无可验证来源",
        "本次检索未返回可验证来源",
    ):
        assert required_text in research


def test_real_browser_gate_requires_public_https_sources_and_no_raw_payload():
    text = OFFICIAL_FLOW_E2E.read_text(encoding="utf-8")

    assert "function isPublicHttpsUrl" in text
    assert 'url.protocol !== "https:"' in text
    assert "reservedHostname(hostname)" in text
    assert "isPublicIpv4(hostname)" in text
    assert "final_url must be a public HTTPS URL" in text
    assert "a[href^=\"https://\"]" in text
    assert 'locator("pre")).toHaveCount(0)' in text


def test_failure_evidence_is_typed_allowlisted_and_visible_to_users():
    schema = PRODUCT_API_SCHEMA.read_text(encoding="utf-8")
    projection = ANALYSIS_PROJECTION.read_text(encoding="utf-8")
    fixture_gate = WORK_PRODUCT_E2E.read_text(encoding="utf-8")
    real_gate = OFFICIAL_FLOW_E2E.read_text(encoding="utf-8")

    for required_text in (
        "productErrorSchema = z.strictObject",
        "code: z.string().trim().min(1)",
        "message: z.string().trim().min(1)",
        "retryable: z.boolean().default(false)",
        "provider: z.string().regex",
        "error_type: z.string().regex",
        "attempt: z.number().int().min(1).max(100)",
    ):
        assert required_text in schema

    assert 'className="failure-panel" role="alert"' in projection
    assert "viewModel.failure.provider" in projection
    assert "viewModel.failure.errorType" in projection
    assert "viewModel.failure.attempt" in projection
    assert "renders only allowlisted research failure diagnostics" in fixture_gate
    for forbidden_field in (
        '"raw_response"',
        '"authorization"',
        '"endpoint"',
        '"correlation_id"',
    ):
        assert forbidden_field in fixture_gate
    assert "failed Product projection must contain a typed honest error" in real_gate
    assert 'type: "observed-product-failure"' in real_gate
    assert "visible-product-failure-${phase}" in real_gate
