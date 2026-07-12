"""commit_final_artifact 节点 - 写入数据库 + 发送通知。

设计文档 7.3 节节点 10：固化最终产物到数据库，发送 Bark 通知。

此节点在 HITL approve 后执行：
1. 写入 analysis_results 到 PostgreSQL
2. 写入 market_snapshots 到 PostgreSQL
3. 写入 decision_results（风控结果）到 PostgreSQL
4. 发送 Bark 通知

Phase 1 实现：
- 数据库写入通过 Repository 模式（storage/repository.py）
- 如果 DB 不可用，降级为只记录日志（不阻断完成）
- 通知通过 send_bark_notification tool

Python 3.10 兼容性：
- 节点为 sync，使用 asyncio.run() 调用异步 DB 和通知
"""

import asyncio
from typing import Any

from crypto_alert_v2.graph.state import AnalysisState


def commit_final_artifact(state: AnalysisState) -> dict[str, Any]:
    """写入数据库 + 发送通知节点。

    只在用户 approve 后执行此节点。
    reject 的请求路由到 blocked 路径，不执行此节点。

    流程：
    1. 写入 analysis_results 到 PostgreSQL
    2. 写入 market_snapshots 到 PostgreSQL
    3. 写入 decision_results（风控结果）
    4. 发送 Bark 通知
    5. 记录 progress_events

    节点为 sync，使用 asyncio.run() 调用异步 DB 和通知。
    """
    final_result = state.get("final_result") or {}
    market_snapshot = state.get("market_snapshot")
    risk_verdict = state.get("risk_verdict") or {}
    run_context = state.get("run_context") or {}
    notification_plan = state.get("notification_plan") or {}

    commit_errors: list[dict[str, Any]] = []
    commit_warnings: list[dict[str, Any]] = []

    # --- 步骤 1-3：写入数据库 ---
    try:
        asyncio.run(_commit_to_database(state, final_result, market_snapshot, risk_verdict, run_context))
    except Exception as exc:
        # DB 写入失败不阻断完成，降级为日志
        commit_warnings.append({
            "stage": "commit_final_artifact",
            "code": "db_write_failed",
            "message": f"数据库写入失败（降级为日志）：{exc}",
        })

    # --- 步骤 4：发送 Bark 通知 ---
    if notification_plan.get("should_send", True):
        try:
            notification_result = asyncio.run(_send_notification(final_result, notification_plan))
            if not notification_result.get("ok"):
                commit_warnings.append({
                    "stage": "commit_final_artifact",
                    "code": "notification_failed",
                    "message": f"Bark 通知发送失败：{notification_result.get('error')}",
                })
        except Exception as exc:
            commit_warnings.append({
                "stage": "commit_final_artifact",
                "code": "notification_error",
                "message": f"Bark 通知异常：{exc}",
            })

    # 更新 final_result 状态
    updated_final_result = {**final_result, "status": "committed"}

    return {
        "final_result": updated_final_result,
        "progress_events": [
            {
                "stage": "commit_final_artifact",
                "status": "completed",
                "run_id": run_context.get("run_id"),
                "notification_sent": notification_plan.get("should_send", True),
            },
        ],
        "warnings": commit_warnings if commit_warnings else [],
    }


async def _commit_to_database(
    state: AnalysisState,
    final_result: dict[str, Any],
    market_snapshot: dict[str, Any] | None,
    risk_verdict: dict[str, Any],
    run_context: dict[str, Any],
) -> None:
    """写入数据库。

    通过 Repository 模式写入 agent_runs, analysis_results, market_snapshots, decision_results。
    如果 PostgreSQL 不可用，抛异常由调用方降级处理。
    """
    from crypto_alert_v2.storage.repository import Repository

    repo = Repository()
    run_id = run_context.get("run_id", "")

    # 写入分析结果
    await repo.save_analysis_result(
        run_id=run_id,
        tenant_id=run_context.get("tenant_id", ""),
        user_id=run_context.get("user_id", ""),
        final_result=final_result,
    )

    # 写入市场快照
    if market_snapshot:
        await repo.save_market_snapshot(
            run_id=run_id,
            snapshot=market_snapshot,
        )

    # 写入风控结果
    await repo.save_decision_result(
        run_id=run_id,
        risk_verdict=risk_verdict,
    )


async def _send_notification(
    final_result: dict[str, Any],
    notification_plan: dict[str, Any],
) -> dict[str, Any]:
    """发送 Bark 通知。"""
    from crypto_alert_v2.tools.notification import send_bark_notification

    body_parts = notification_plan.get("body_parts", {})

    result = await send_bark_notification.ainvoke({
        "symbol": final_result.get("instrument", ""),
        "action": final_result.get("main_action", ""),
        "probability": final_result.get("probability", 0.0),
        "entry_trigger": body_parts.get("entry_trigger"),
        "stop_price": body_parts.get("stop_price"),
        "target_1": body_parts.get("target_1"),
        "target_2": body_parts.get("target_2"),
        "risk_pct": body_parts.get("risk_pct"),
        "max_leverage": body_parts.get("max_leverage"),
        "why_not_opposite": body_parts.get("why_not_opposite", ""),
        "expires_in_seconds": body_parts.get("expires_in_seconds", 90),
        "risk_allowed": body_parts.get("risk_allowed", True),
        "blocked_reasons": body_parts.get("blocked_reasons", []),
        "warnings": body_parts.get("warnings", []),
        "unavailable_data": body_parts.get("unavailable_data", []),
    })

    return result
