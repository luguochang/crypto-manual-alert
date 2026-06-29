from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from crypto_manual_alert.context.request import build_manual_decision_request

from .schemas import ManualRunRequest, failure, success


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("/manual")
def create_manual_run(payload: ManualRunRequest, request: Request) -> dict:
    """创建一次同步手动运行，并返回前端轮询需要的 trace_id。"""

    decision_request = build_manual_decision_request(payload)
    result = request.app.state.executor.submit(decision_request)
    data = {"trace_id": result.trace_id, "plan": result.plan, "verdict": result.verdict}
    return success(data, trace_id=result.trace_id)


@router.get("")
def list_runs(request: Request, limit: int = 20) -> dict:
    """列出最近运行记录，默认只返回摘要和计数字段。"""

    return success({"items": request.app.state.query_repository.list_runs(limit=limit)})


@router.get("/{trace_id}")
def get_run_detail(trace_id: str, request: Request, include_payloads: bool = False) -> dict:
    """查询单次运行详情；include_payloads=true 时返回已脱敏的 LLM 请求/返回。"""

    detail = request.app.state.query_repository.get_run_detail(trace_id, include_payloads=include_payloads)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=failure(code="trace_not_found", message="trace not found", trace_id=trace_id),
        )
    return success(detail, trace_id=trace_id)
