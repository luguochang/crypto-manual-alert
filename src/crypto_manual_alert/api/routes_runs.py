from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from crypto_manual_alert.context.request import build_manual_decision_request

from .diagnostic_guard import require_diagnostic_routes_enabled
from .schemas import ManualRunRequest, failure, success


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("/manual")
def create_manual_run(payload: ManualRunRequest, request: Request) -> dict:
    """创建一次同步手动运行，并返回前端轮询需要的 trace_id。"""

    decision_request = build_manual_decision_request(payload)
    result = request.app.state.executor.submit(decision_request)
    detail = request.app.state.query_repository.get_run_detail(result.trace_id)
    if not isinstance(detail, dict):
        _raise_manual_projection_error(
            "manual_run_projection_missing_detail",
            "manual run completed but persisted run detail could not be read back",
            result.trace_id,
        )
    plan_run = detail.get("plan_run") if isinstance(detail, dict) else None
    if not isinstance(plan_run, dict):
        _raise_manual_projection_error(
            "manual_run_projection_missing_plan_run",
            "manual run completed but persisted plan_run projection is missing",
            result.trace_id,
        )
    business_summary = plan_run.get("business_summary")
    if not isinstance(business_summary, dict):
        _raise_manual_projection_error(
            "manual_run_projection_missing_business_summary",
            "manual run completed but persisted business_summary projection is missing",
            result.trace_id,
        )
    result_review = detail.get("result_review")
    if not isinstance(result_review, dict):
        _raise_manual_projection_error(
            "manual_run_projection_missing_result_review",
            "manual run completed but result_review projection is missing",
            result.trace_id,
        )

    notification = detail.get("notification")
    parsed_plan = plan_run.get("parsed_plan")
    response_plan = {
        **(parsed_plan if isinstance(parsed_plan, dict) else {}),
        **result.plan,
    }
    data = {
        "trace_id": result.trace_id,
        "plan": response_plan,
        "verdict": plan_run.get("verdict") or result.verdict,
        "business_summary": business_summary,
        "main_path_contract": plan_run.get("main_path_contract"),
        "notification": notification,
        "result_review": result_review,
    }
    return success(data, trace_id=result.trace_id)


@router.get("")
def list_runs(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    symbol: str | None = None,
    allowed: bool | None = None,
) -> dict:
    """列出最近运行记录，默认只返回摘要和计数字段。"""

    page_limit = request.app.state.query_repository.normalize_limit(limit)
    page_offset = request.app.state.query_repository.normalize_offset(offset)
    items = request.app.state.query_repository.list_runs(
        limit=page_limit + 1,
        offset=page_offset,
        status=status,
        symbol=symbol,
        allowed=allowed,
    )
    has_more = len(items) > page_limit
    return success(
        {
            "items": items[:page_limit],
            "limit": page_limit,
            "offset": page_offset,
            "has_more": has_more,
            "next_offset": page_offset + page_limit if has_more else None,
        }
    )


@router.get("/{trace_id}")
def get_run_detail(trace_id: str, request: Request, include_payloads: bool = False) -> dict:
    """查询单次运行详情；include_payloads=true 时返回已脱敏的 LLM 请求/返回。"""

    if include_payloads:
        require_diagnostic_routes_enabled(request)
    detail = request.app.state.query_repository.get_run_detail(trace_id, include_payloads=include_payloads)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=failure(code="trace_not_found", message="trace not found", trace_id=trace_id),
        )
    return success(detail, trace_id=trace_id)


def _raise_manual_projection_error(code: str, message: str, trace_id: str) -> None:
    raise HTTPException(
        status_code=500,
        detail=failure(code=code, message=message, trace_id=trace_id),
    )
