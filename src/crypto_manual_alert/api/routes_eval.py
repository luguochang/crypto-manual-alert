from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from crypto_manual_alert.eval.errors import EvalRunError
from crypto_manual_alert.eval.guards import EvalSafetyError
from crypto_manual_alert.eval.runner import SUPPORTED_MODES
from crypto_manual_alert.eval.schema import EvalFrozenInput

from .diagnostic_guard import require_diagnostic_routes_enabled
from .schemas import EvalRunRequest, failure, success


router = APIRouter(prefix="/api/eval", tags=["eval"])


@router.get("/candidates")
def list_eval_candidates(
    request: Request,
    dataset: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> dict:
    """列出可进入 eval 的 badcase 候选，默认只返回脱敏 trace 摘要。"""

    items = request.app.state.eval_case_builder.list_candidates(
        dataset=dataset,
        status=status,
        severity=severity,
        limit=limit,
    )
    return success({"items": items})


@router.get("/runs")
def list_eval_runs(request: Request, limit: int = 20) -> dict:
    """列出旁路 eval run，不混入生产 runs 列表。"""

    diagnostic_enabled = _diagnostic_routes_enabled(request)
    return success(
        {
            "items": [
                _eval_run_summary_for_response(item, diagnostic_enabled=diagnostic_enabled)
                for item in request.app.state.eval_store.list_runs(limit=limit)
            ]
        }
    )


@router.get("/outcomes")
def list_eval_outcomes(
    request: Request,
    evaluation_target: str | None = None,
) -> dict:
    """列出 eval sidecar outcomes，供金融质量面板展示样本。

    outcome 来自 `crypto-alert collect-outcomes` 写入的 OutcomeStore（旁路 eval
    sidecar）或显式本地 mock seed。`source_type=mocked_outcome` 只用于本地
    可见性证明，不影响生产决策，也不进入真实金融质量评分；只有
    `exchange_native` 成熟样本可用于真实 advisory quality metrics。未收集时
    返回空列表，金融质量 gate 仍为 not_enough_samples。
    """

    outcomes = request.app.state.outcome_store.list_outcomes(
        evaluation_target=evaluation_target
    )
    return success({"items": [outcome.to_public_dict() for outcome in outcomes]})


@router.post("/runs")
def create_eval_run(payload: EvalRunRequest, request: Request) -> dict:
    """运行一次 fixture judge eval。

    首版只支持 judge_only_fixture，避免默认访问真实 LLM 或外部网络。
    """

    if payload.mode not in SUPPORTED_MODES:
        raise HTTPException(
            status_code=400,
            detail=failure(
                code="eval_mode_not_supported",
                message=f"supported eval modes: {', '.join(sorted(SUPPORTED_MODES))}",
            ),
        )
    if payload.mode == "judge_openai":
        require_diagnostic_routes_enabled(request)
    try:
        run = request.app.state.eval_runner.run(
            dataset_name=payload.dataset_name,
            badcase_ids=payload.badcase_ids,
            mode=payload.mode,
            limit=payload.limit,
        )
    except EvalSafetyError as exc:
        raise HTTPException(
            status_code=400,
            detail=failure(code=exc.code, message=str(exc)),
        ) from exc
    except ValueError as exc:
        code = "eval_no_cases" if str(exc) == "no eval cases selected" else "eval_run_failed"
        raise HTTPException(
            status_code=400,
            detail=failure(code=code, message=str(exc)),
        ) from exc
    except EvalRunError as exc:
        raise HTTPException(
            status_code=500,
            detail=failure(code=exc.code, message=str(exc)),
        ) from exc
    return success(_eval_run_summary_for_response(run.__dict__, diagnostic_enabled=_diagnostic_routes_enabled(request)))


@router.get("/runs/{eval_run_id}")
def get_eval_run_detail(eval_run_id: str, request: Request) -> dict:
    """返回 eval run、case、score 明细，供前端复盘每个 judge 的判断。"""

    require_diagnostic_routes_enabled(request)
    detail = request.app.state.eval_store.get_run_detail(eval_run_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=failure(code="eval_run_not_found", message="eval run not found"),
        )
    return success(detail)


@router.get("/runs/{eval_run_id}/promotion-artifacts")
def get_eval_promotion_artifacts(eval_run_id: str, request: Request) -> dict:
    """读取 eval sidecar promotion artifacts，不改变生产 final input。"""

    require_diagnostic_routes_enabled(request)
    detail = request.app.state.eval_store.get_run_detail(eval_run_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=failure(code="eval_run_not_found", message="eval run not found"),
        )
    artifacts = request.app.state.eval_store.get_promotion_artifacts(eval_run_id)
    return success({"artifacts": artifacts})


@router.get("/cases/{case_id}/frozen-input")
def get_eval_case_frozen_input(case_id: str, request: Request) -> dict:
    """读取 eval case 的 frozen input public summary，避免暴露完整 replay payload。"""

    case = request.app.state.eval_store.get_case(case_id)
    if case is None:
        raise HTTPException(
            status_code=404,
            detail=failure(code="eval_case_not_found", message="eval case not found"),
        )
    frozen = request.app.state.eval_store.get_frozen_input(case.frozen_input_hash)
    if frozen is None:
        raise HTTPException(
            status_code=404,
            detail=failure(code="eval_frozen_input_not_found", message="eval frozen input not found"),
        )
    return success({"frozen_input": _public_frozen_input(frozen)})


@router.get("/frozen-inputs/{frozen_input_hash}")
def get_eval_frozen_input_by_hash(frozen_input_hash: str, request: Request) -> dict:
    """按 frozen_input_hash 读取 public summary，避免历史 case hash 漂移。"""

    frozen = request.app.state.eval_store.get_frozen_input(frozen_input_hash)
    if frozen is None:
        raise HTTPException(
            status_code=404,
            detail=failure(code="eval_frozen_input_not_found", message="eval frozen input not found"),
        )
    return success({"frozen_input": _public_frozen_input(frozen)})


def _public_frozen_input(frozen: EvalFrozenInput) -> dict:
    return {
        "frozen_input_hash": frozen.frozen_input_hash,
        "schema_version": frozen.schema_version,
        "kind": frozen.kind,
        "source_trace_id": frozen.source_trace_id,
        "source_badcase_id": frozen.source_badcase_id,
        "public_summary": frozen.public_summary,
        "metadata": frozen.metadata,
    }


def _diagnostic_routes_enabled(request: Request) -> bool:
    config = getattr(request.app.state, "config", None)
    diagnostic = getattr(config, "diagnostic", None)
    return bool(getattr(diagnostic, "routes_enabled", False))


def _eval_run_summary_for_response(run: dict, *, diagnostic_enabled: bool) -> dict:
    if diagnostic_enabled:
        return run
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    public_metadata: dict[str, object] = {}
    if isinstance(metadata.get("financial_quality_gate"), dict):
        public_metadata["financial_quality_gate"] = metadata["financial_quality_gate"]
    return {**run, "metadata": public_metadata}
