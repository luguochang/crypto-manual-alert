from __future__ import annotations

from pathlib import Path


FRONTEND_SRC = Path("frontend/src")
WORK_ROUTE = FRONTEND_SRC / "app" / "work" / "page.tsx"
RUNS_ROUTE = FRONTEND_SRC / "app" / "runs" / "page.tsx"
PRIMARY_NAVIGATION = FRONTEND_SRC / "components" / "primary-navigation.tsx"
WORK_SURFACE = FRONTEND_SRC / "features" / "work" / "work-surface.tsx"
RUNS_SURFACE = FRONTEND_SRC / "features" / "runs" / "runs-surface.tsx"
DATA_LIFECYCLE_CONTROLS = (
    FRONTEND_SRC / "features" / "settings" / "data-lifecycle-controls.tsx"
)
OFFICIAL_RUN_STREAM = (
    FRONTEND_SRC / "features" / "agent-runtime" / "official-run-stream.tsx"
)
WORK_PRODUCT_E2E = Path("frontend/tests/e2e-v2/work-product.spec.ts")
V2_IMPLEMENTATION_STATUS = Path("docs/v2/15-v2-implementation-status.md")


def test_work_and_runs_routes_keep_product_ownership_in_feature_surfaces():
    work_route = WORK_ROUTE.read_text(encoding="utf-8")
    runs_route = RUNS_ROUTE.read_text(encoding="utf-8")
    navigation = PRIMARY_NAVIGATION.read_text(encoding="utf-8")

    assert 'import { WorkSurface } from "@/features/work/work-surface";' in work_route
    assert "return <WorkSurface />;" in work_route
    assert 'import { RunsSurface } from "@/features/runs/runs-surface";' in runs_route
    assert "return <RunsSurface />;" in runs_route
    assert _line_count(WORK_ROUTE) <= 10
    assert _line_count(RUNS_ROUTE) <= 10
    assert '{ label: "工作台", icon: BriefcaseBusiness, href: "/work" }' in navigation
    assert '{ label: "运行记录", icon: History, href: "/runs" }' in navigation


def test_work_route_uses_typed_product_api_and_official_stream_projection():
    source = WORK_SURFACE.read_text(encoding="utf-8")

    assert 'import { AnalysisProjection } from "@/features/analysis/analysis-projection";' in source
    assert 'from "@/features/agent-runtime/official-run-stream";' in source
    assert "OfficialRunStream" in source
    assert 'cancelTask,' in source
    assert 'createAnalysis,' in source
    assert 'getTask,' in source
    assert 'ProductApiError,' in source
    assert 'from "@/lib/api/product-client";' in source
    assert 'from "@/lib/schemas/product-api";' in source
    assert "query_text: query" in source
    assert "<OfficialRunStream" in source
    assert "<AnalysisProjection" in source


def test_runs_route_reads_persisted_products_and_links_historical_run_selection():
    source = RUNS_SURFACE.read_text(encoding="utf-8")

    assert 'import { listRuns, ProductApiError } from "@/lib/api/product-client";' in source
    assert 'import type { ProductRunSummary } from "@/lib/schemas/product-api";' in source
    assert "const response = await listRuns(25);" in source
    assert "<li key={run.run_id}>" in source
    assert "href={`/runs/${encodeURIComponent(run.run_id)}`}" in source


def test_official_stream_uses_langchain_react_and_same_origin_agent_bff():
    source = OFFICIAL_RUN_STREAM.read_text(encoding="utf-8")

    assert 'import { useChannel, useStream } from "@langchain/react";' in source
    assert "useChannel(stream, productCustomChannels" in source
    assert "const stream = useStream<OfficialExecutionValues>({" in source
    assert 'return new URL("/api/agent", baseUrl).toString();' in source
    assert "apiUrl: officialAgentApiUrl(window.location.origin)" in source
    assert 'transport: "sse"' in source


def test_historical_run_does_not_attach_the_live_thread_head():
    work = WORK_SURFACE.read_text(encoding="utf-8")
    stream = OFFICIAL_RUN_STREAM.read_text(encoding="utf-8")
    browser_gate = WORK_PRODUCT_E2E.read_text(encoding="utf-8")

    assert "setHistoricalRunSelection(selectedRunId !== null)" in work
    assert "export function shouldAttachOfficialStream(" in work
    assert "const streamEligible = shouldAttachOfficialStream(task, historicalRunSelection);" in work
    assert "&& !historicalRunSelection" in work
    assert "&& !terminalStatuses.has(task.status)" in work
    assert "&& task.cancel_requested_at === null" in work
    assert "&& streamEligible" in work
    assert "{activeStreamBinding && !historicalRunSelection ? (" in work
    assert "const { assistant_id: assistantId, thread_id: threadId } = binding;" in stream
    assert "runId:" not in stream
    assert (
        'test("does not attach the Thread head stream while viewing historical Run output"'
        in browser_gate
    )


def test_v2_product_surfaces_do_not_render_raw_json_or_preformatted_payloads():
    product_sources = [
        *sorted((FRONTEND_SRC / "app").rglob("*.tsx")),
        *sorted((FRONTEND_SRC / "components").rglob("*.tsx")),
        *sorted((FRONTEND_SRC / "features").rglob("*.tsx")),
    ]
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in product_sources
    )

    assert "<dl" in combined
    assert "<ol" in combined
    assert "<pre" not in combined
    sources_with_json_serialization = [
        path
        for path in product_sources
        if "JSON.stringify(" in path.read_text(encoding="utf-8")
    ]
    assert sources_with_json_serialization == [DATA_LIFECYCLE_CONTROLS]
    lifecycle_source = DATA_LIFECYCLE_CONTROLS.read_text(encoding="utf-8")
    assert lifecycle_source.count("JSON.stringify(") == 1
    assert (
        'new Blob([JSON.stringify(value, null, 2)], { type: "application/json" })'
        in lifecycle_source
    )
    assert "Raw JSON" not in combined


def test_retired_v1_diagnostics_are_not_misrepresented_as_completed_v2_parity():
    status = V2_IMPLEMENTATION_STATUS.read_text(encoding="utf-8")

    for retired_path in (
        FRONTEND_SRC / "app" / "eval" / "page.tsx",
        FRONTEND_SRC / "app" / "config" / "page.tsx",
        FRONTEND_SRC / "app" / "runs" / "[traceId]" / "agent-audit-panel.tsx",
        FRONTEND_SRC / "app" / "runs" / "[traceId]" / "notification-history.tsx",
        FRONTEND_SRC / "lib" / "schemas" / "manual-run.ts",
        FRONTEND_SRC / "lib" / "schemas" / "runs.ts",
    ):
        assert not retired_path.exists(), retired_path

    for tracked_gap in (
        "V2 = PARTIAL",
        "Production Ready = NO",
        "licensed persistent Agent Server",
        "V1 parity/removal 均不存在",
    ):
        assert tracked_gap in status


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())
