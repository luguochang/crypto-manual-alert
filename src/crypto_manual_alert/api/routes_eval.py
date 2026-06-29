from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from crypto_manual_alert.eval.errors import EvalRunError
from crypto_manual_alert.eval.guards import EvalSafetyError
from crypto_manual_alert.eval.runner import SUPPORTED_MODES

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

    return success({"items": request.app.state.eval_store.list_runs(limit=limit)})


@router.get("/outcomes")
def list_eval_outcomes(
    request: Request,
    evaluation_target: str | None = None,
) -> dict:
    """列出已收集的市场 outcome，供金融质量面板展示真实样本。

    outcome 来自 `crypto-alert collect-outcomes` 写入的 OutcomeStore（旁路 eval
    sidecar），不影响生产决策。未收集时返回空列表，金融质量 gate 仍为
    not_enough_samples。
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
    return success(run.__dict__)


@router.get("/runs/{eval_run_id}")
def get_eval_run_detail(eval_run_id: str, request: Request) -> dict:
    """返回 eval run、case、score 明细，供前端复盘每个 judge 的判断。"""

    detail = request.app.state.eval_store.get_run_detail(eval_run_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=failure(code="eval_run_not_found", message="eval run not found"),
        )
    return success(detail)
