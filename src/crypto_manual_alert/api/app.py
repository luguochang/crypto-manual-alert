from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from crypto_manual_alert.config import Config, load_config
from crypto_manual_alert.eval.case_builder import EvalCaseBuilder
from crypto_manual_alert.eval.outcome_store import OutcomeStore
from crypto_manual_alert.eval.runner import EvalRunner, eval_store_path, outcome_store_path
from crypto_manual_alert.eval.store import EvalStore
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.storage.query_repository import JournalQueryRepository
from crypto_manual_alert.workflow.executor import RunExecutor
from crypto_manual_alert.workflow.legacy_plan_runner import journal_path

from .routes_eval import router as eval_router
from .routes_runs import router as runs_router
from .routes_system import router as system_router


def create_app(config_paths: list[str] | None = None, data_dir: str | Path | None = None) -> FastAPI:
    """创建 FastAPI 应用。

    data_dir 只用于测试或本地覆盖数据目录，不改变 YAML 配置文件本身。
    """

    effective_config_paths = config_paths if config_paths is not None else _config_paths_from_env()
    config = _load_app_config(effective_config_paths, data_dir=data_dir)
    journal = Journal(journal_path(config))
    eval_store = EvalStore(eval_store_path(config.app.data_dir))
    outcome_store = OutcomeStore(outcome_store_path(config.app.data_dir))
    app = FastAPI(title="crypto-manual-alert", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://localhost:3000",
            "http://localhost:3001",
        ],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type"],
    )
    app.state.config = config
    app.state.journal = journal
    app.state.query_repository = JournalQueryRepository(journal, outcome_store=outcome_store, config=config)
    app.state.executor = RunExecutor(config=config, journal=journal)
    app.state.eval_store = eval_store
    app.state.outcome_store = outcome_store
    app.state.eval_case_builder = EvalCaseBuilder(journal)
    app.state.eval_runner = EvalRunner(
        journal=journal,
        store=eval_store,
        outcome_store=outcome_store,
        data_dir=config.app.data_dir,
        forbidden_env_names=config.security.forbidden_env_names,
        config=config,
    )
    app.include_router(system_router)
    app.include_router(runs_router)
    app.include_router(eval_router)
    app.add_exception_handler(RequestValidationError, _request_validation_exception_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
    return app


def _load_app_config(config_paths: list[str], data_dir: str | Path | None) -> Config:
    config = load_config(*config_paths)
    if data_dir is None:
        return config
    return replace(config, app=replace(config.app, data_dir=str(data_dir)))


def _config_paths_from_env() -> list[str]:
    raw = os.getenv("CONFIG_PATHS", "").strip()
    if not raw:
        return []
    separator = os.pathsep if os.pathsep in raw else ","
    return [item.strip() for item in raw.split(separator) if item.strip()]


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底异常处理，避免接口返回非结构化错误。"""

    status_code = getattr(exc, "status_code", 500)
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "data": None,
            "error": {
                "code": "internal_error",
                "message": "internal server error",
                "detail": {"type": type(exc).__name__},
            },
            "trace_id": None,
        },
    )


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """处理业务主动抛出的 HTTPException，保留统一 API envelope。"""

    if isinstance(exc.detail, dict) and "ok" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "data": None,
            "error": {
                "code": "http_error",
                "message": str(exc.detail),
                "detail": {},
            },
            "trace_id": None,
        },
    )


async def _request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """处理 FastAPI/Pydantic 请求校验错误，保持统一 API envelope。"""

    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "data": None,
            "error": {
                "code": "validation_error",
                "message": "request validation failed",
                "details": exc.errors(),
            },
            "trace_id": None,
        },
    )


app = create_app()
