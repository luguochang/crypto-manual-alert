from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import ipaddress
import json
from typing import Any, Literal, cast
from urllib.parse import urlparse
from uuid import uuid4

from langgraph_sdk import get_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.agent_server import (
    AgentServerRunner,
    RemoteInterruptSet,
    RemoteRunHandle,
)
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import Settings, get_settings
from crypto_alert_v2.persistence.models import (
    InterruptPause,
    InterruptProjection,
    Run,
    Task,
    Tenant,
    Thread,
    User,
    Workspace,
)


ASSISTANT_ID = "crypto_analysis"
MULTI_INTERRUPT_ASSISTANT_ID = "multi_interrupt_fixture"
FixtureKind = Literal["canonical", "deep_research", "multi_interrupt"]
FIXTURE_ASSISTANTS: dict[FixtureKind, str] = {
    "canonical": ASSISTANT_ID,
    "deep_research": ASSISTANT_ID,
    "multi_interrupt": MULTI_INTERRUPT_ASSISTANT_ID,
}
FIXTURE_INTERRUPT_COUNTS: dict[FixtureKind, int] = {
    "canonical": 1,
    "deep_research": 1,
    "multi_interrupt": 2,
}
FIXTURE_ACTOR = ActorContext(
    tenant_id="dev-tenant",
    workspace_id="dev-workspace",
    user_id="dev-user",
    roles=("analyst",),
    permissions=("analysis:read", "analysis:write"),
)
REQUEST = {
    "symbol": "BTC-USDT-SWAP",
    "horizon": "4h",
    "query_text": "审核已持久化的 BTC 风险分析草稿。",
    "notify": False,
}
ANALYSIS = {
    "regime": "risk_on",
    "horizon": "4h",
    "risk_pct": "0.1",
    "target_1": "66000",
    "target_2": "67000",
    "instrument": "BTC-USDT-SWAP",
    "stop_price": "64500",
    "main_action": "open_long",
    "probability": 0.65,
    "total_score": 2,
    "invalidation": "Close below 64500.",
    "max_leverage": 2,
    "entry_trigger": "65100",
    "factor_scores": {"macro": 0, "derivatives": 1, "market_structure": 1},
    "reference_price": "65000.25",
    "root_cause_chain": [
        "Price reclaimed resistance",
        "Liquidity supports continuation",
    ],
    "unavailable_data": [],
    "why_not_opposite": "The bearish invalidation has not triggered.",
    "expires_in_seconds": 90,
    "position_size_class": "light",
    "manual_execution_required": True,
}
EVIDENCE_VERDICT = {
    "warnings": [],
    "sufficient": True,
    "confidence_cap": 1.0,
    "missing_optional": [],
    "missing_required": [],
}
RISK_VERDICT = {
    "allowed": True,
    "warnings": [],
    "confidence_cap": 1.0,
    "blocked_reasons": [],
}
ARTIFACT = {
    "status": "draft",
    "analysis": ANALYSIS,
    "risk_verdict": RISK_VERDICT,
    "artifact_type": "analysis_report",
    "schema_version": "1.0",
    "content_version": 1,
    "evidence_verdict": EVIDENCE_VERDICT,
    "source_references": ["https://www.reuters.com/markets/currencies/"],
}
GRAPH_STATE = {
    "request": REQUEST,
    "analysis": ANALYSIS,
    "evidence_verdict": EVIDENCE_VERDICT,
    "risk_verdict": RISK_VERDICT,
    "artifact": ARTIFACT,
    "web_evidence": [],
    "review_policy": "required",
    "review_iteration": 0,
    "terminal_status": "running",
    "errors": [],
    "lifecycle": "artifact_built",
}
DEEP_RESEARCH_REQUEST = {
    "task_type": "deep_research",
    "symbol": "BTC-USDT-SWAP",
    "horizon": "7d",
    "query_text": "审核已持久化的 BTC 机构采用研究草稿。",
}
DEEP_RESEARCH_EVIDENCE = {
    "query": "BTC institutional adoption",
    "final_url": "https://example.com/verified-institutional-source",
    "redirect_chain": [],
    "http_status": 200,
    "fetched_at": "2026-07-19T08:00:00Z",
    "published_at": "2026-07-19T07:00:00Z",
    "content_hash": "a" * 64,
    "parser_version": "controlled-hitl-seed-v1",
    "title": "Verified institutional source",
    "author": "Research Desk",
    "source": "controlled_hitl_seed",
    "excerpt": "A verified source records continued institutional product activity.",
    "evidence_relation": "supports",
}
DEEP_RESEARCH_ARTIFACT = {
    "artifact_type": "deep_research_report",
    "schema_version": "1.0",
    "status": "draft",
    "harness_mode": "deepagents",
    "search_coverage": {
        "status": "complete",
        "attempted_queries": 1,
        "successful_queries": 1,
        "failed_queries": [],
    },
    "report": {
        "executive_summary": "BTC 机构采用仍在推进，但需要保留反证空间。",
        "sections": [
            {
                "title": "机构采用",
                "summary": "可验证来源支持该趋势，但样本窗口仍然有限。",
                "findings": [
                    {
                        "claim": "机构产品活动保持增长。",
                        "source_indexes": [1],
                    }
                ],
            }
        ],
        "risk_notes": ["事件窗口可能快速改变当前判断。"],
        "evidence_gaps": ["缺少跨周期资金流样本。"],
    },
    "sources": [{"index": 1, "evidence": DEEP_RESEARCH_EVIDENCE}],
    "model_audits": [],
}
DEEP_RESEARCH_GRAPH_STATE = {
    "request": DEEP_RESEARCH_REQUEST,
    "task_type": "deep_research",
    "deep_research_artifact": DEEP_RESEARCH_ARTIFACT,
    "web_evidence": [DEEP_RESEARCH_EVIDENCE],
    "model_audits": [],
    "research_harness_mode": "deepagents",
    "review_policy": "required",
    "review_iteration": 0,
    "terminal_status": "running",
    "errors": [],
    "lifecycle": "deep_research_draft_ready",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed canonical official HITL checkpoints for real browser QA."
    )
    parser.add_argument("--count", type=int, default=1, choices=range(1, 11))
    parser.add_argument("--label-prefix", default="browser")
    parser.add_argument("--ttl-seconds", type=int, default=1800)
    parser.add_argument(
        "--fixture",
        choices=tuple(FIXTURE_ASSISTANTS),
        default="canonical",
    )
    return parser


def _loopback_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"} or hostname is None:
        return False
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _authorization(settings: Settings) -> str:
    if not _loopback_url(settings.agent_server_url):
        raise RuntimeError("HITL E2E seeding is restricted to a loopback Agent Server")
    if settings.app_environment not in {"development", "local", "test"}:
        raise RuntimeError(
            "HITL E2E seeding is disabled outside local test environments"
        )
    token = settings.agent_server_local_token
    if token is None or not token.get_secret_value().strip():
        raise RuntimeError("AGENT_SERVER_LOCAL_TOKEN is required")
    return f"Bearer {token.get_secret_value()}"


def _request_hash(request: dict[str, Any] = REQUEST) -> str:
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _interrupt_member_set_hash(interrupt_set: RemoteInterruptSet) -> str:
    root_checkpoint = interrupt_set.checkpoint
    members = [
        {
            "interrupt_id": item.interrupt_id,
            "namespace": item.namespace,
            "checkpoint_id": item.checkpoint_id,
        }
        for item in sorted(interrupt_set.interrupts, key=lambda item: item.interrupt_id)
    ]
    canonical = json.dumps(
        {
            "root_checkpoint": {
                "thread_id": root_checkpoint.thread_id,
                "checkpoint_ns": root_checkpoint.checkpoint_ns,
                "checkpoint_id": root_checkpoint.checkpoint_id,
                "checkpoint_map": root_checkpoint.checkpoint_map,
            },
            "members": members,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _resolved_actor_ids(
    session_factory: async_sessionmaker[Any],
) -> tuple[Any, Any, Any]:
    async with session_factory() as session, session.begin():
        tenant = await session.scalar(
            select(Tenant).where(Tenant.external_id == FIXTURE_ACTOR.tenant_id)
        )
        if tenant is None:
            raise RuntimeError("fixture tenant was not provisioned")
        user = await session.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.external_subject == FIXTURE_ACTOR.user_id,
            )
        )
        workspace = await session.scalar(
            select(Workspace).where(
                Workspace.tenant_id == tenant.id,
                Workspace.external_id == FIXTURE_ACTOR.workspace_id,
            )
        )
        if user is None or workspace is None:
            raise RuntimeError("fixture user or workspace was not provisioned")
        workspace.review_policy = "required"
        return tenant.id, workspace.id, user.id


async def _seed_one(
    *,
    client: Any,
    runner: AgentServerRunner,
    session_factory: async_sessionmaker[Any],
    actor_ids: tuple[Any, Any, Any],
    authorization: str,
    label: str,
    ttl_seconds: int,
    fixture: FixtureKind,
) -> dict[str, Any]:
    tenant_id, workspace_id, user_id = actor_ids
    thread_id = uuid4()
    task_id = uuid4()
    product_run_id = uuid4()
    headers = {"authorization": authorization}
    metadata = {
        "tenant_id": FIXTURE_ACTOR.tenant_id,
        "workspace_id": FIXTURE_ACTOR.workspace_id,
        "user_id": FIXTURE_ACTOR.user_id,
        "task_id": str(task_id),
        "product_run_id": str(product_run_id),
        "fixture": label,
        "fixture_kind": fixture,
    }
    assistant_id = FIXTURE_ASSISTANTS[fixture]
    await client.threads.create(
        thread_id=str(thread_id),
        graph_id=assistant_id,
        metadata=metadata,
        headers=headers,
    )
    try:
        initial_input: dict[str, Any] | None
        if fixture == "canonical":
            await client.threads.update_state(
                str(thread_id),
                GRAPH_STATE,
                as_node="build_artifact",
                headers=headers,
            )
            initial_input = None
        elif fixture == "deep_research":
            await client.threads.update_state(
                str(thread_id),
                DEEP_RESEARCH_GRAPH_STATE,
                as_node="run_deep_research",
                headers=headers,
            )
            initial_input = None
        else:
            initial_input = {"completion_count": 0}
        raw_run = await client.runs.create(
            str(thread_id),
            assistant_id,
            input=initial_input,
            durability="sync",
            metadata=metadata,
            headers=headers,
        )
        handle = RemoteRunHandle(
            assistant_id=str(raw_run["assistant_id"]),
            thread_id=str(thread_id),
            run_id=str(raw_run["run_id"]),
            authorization=authorization,
        )
        raw_status = "unknown"
        normalized_status = "unknown"
        for _ in range(100):
            remote = await client.runs.get(
                str(thread_id), handle.run_id, headers=headers
            )
            raw_status = str(remote.get("status"))
            normalized_status = (await runner.get(handle)).status
            if normalized_status == "interrupted":
                break
            await asyncio.sleep(0.05)
        if normalized_status != "interrupted":
            raise RuntimeError(
                "official fixture did not reach a canonical interrupt "
                f"(raw={raw_status}, normalized={normalized_status})"
            )
        interrupt_set = await runner.get_interrupts(handle)
        expected_interrupt_count = FIXTURE_INTERRUPT_COUNTS[fixture]
        if len(interrupt_set) != expected_interrupt_count:
            raise RuntimeError(
                f"expected {expected_interrupt_count} {fixture} official "
                f"interrupt(s), got {len(interrupt_set)}"
            )
        root_checkpoint = interrupt_set.checkpoint
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)
        pause_id = uuid4()
        request_payload = (
            DEEP_RESEARCH_REQUEST if fixture == "deep_research" else REQUEST
        )
        task_type = "deep_research" if fixture == "deep_research" else "market_analysis"
        async with session_factory() as session, session.begin():
            session.add(
                Thread(
                    id=thread_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_user_id=user_id,
                    official_thread_id=str(thread_id),
                    title=(
                        f"BTC-USDT-SWAP "
                        f"{'7d' if fixture == 'deep_research' else '4h'} "
                        f"{label} review"
                    ),
                    context={"fixture": "official-hitl-e2e"},
                )
            )
            await session.flush()
            session.add(
                Task(
                    id=task_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_user_id=user_id,
                    thread_id=thread_id,
                    task_type=task_type,
                    status="waiting_human",
                    idempotency_key=f"hitl-{label}-{uuid4()}",
                    request_payload_hash=_request_hash(request_payload),
                    request_payload=request_payload,
                    completed_at=None,
                )
            )
            await session.flush()
            session.add(
                Run(
                    id=product_run_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_user_id=user_id,
                    thread_id=thread_id,
                    task_id=task_id,
                    attempt=1,
                    status="waiting_human",
                    official_assistant_id=handle.assistant_id,
                    official_run_id=handle.run_id,
                    checkpoint_id=root_checkpoint.checkpoint_id,
                    input_payload=request_payload,
                    output_payload=None,
                    failure_code=None,
                    failure_message=None,
                    started_at=now,
                    finished_at=None,
                    last_heartbeat_at=now,
                    reconciliation_deadline_at=None,
                    projection_fence=0,
                    terminal_output_hash=None,
                    cancel_requested_at=None,
                    observed_terminal_status=None,
                    resume_of_run_id=None,
                )
            )
            await session.flush()
            session.add(
                InterruptPause(
                    id=pause_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_user_id=user_id,
                    task_id=task_id,
                    run_id=product_run_id,
                    pause_version=1,
                    root_thread_id=root_checkpoint.thread_id,
                    root_checkpoint_ns=root_checkpoint.checkpoint_ns,
                    root_checkpoint_id=root_checkpoint.checkpoint_id,
                    root_checkpoint_map=root_checkpoint.checkpoint_map,
                    member_set_hash=_interrupt_member_set_hash(interrupt_set),
                    status="pending",
                    expires_at=expires_at,
                )
            )
            await session.flush()
            session.add_all(
                [
                    InterruptProjection(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        workspace_id=workspace_id,
                        owner_user_id=user_id,
                        task_id=task_id,
                        run_id=product_run_id,
                        pause_id=pause_id,
                        official_interrupt_id=remote_interrupt.interrupt_id,
                        namespace=remote_interrupt.namespace,
                        checkpoint_id=remote_interrupt.checkpoint_id,
                        response_version=1,
                        status="pending",
                        payload=remote_interrupt.value,
                        expires_at=expires_at,
                        responded_at=None,
                    )
                    for remote_interrupt in interrupt_set.interrupts
                ]
            )
        return {
            "label": label,
            "fixture": fixture,
            "assistant_id": assistant_id,
            "member_count": len(interrupt_set),
            "task_id": str(task_id),
            "product_run_id": str(product_run_id),
            "official_raw_status": raw_status,
            "normalized_status": normalized_status,
            "product_status": "waiting_human",
        }
    except BaseException:
        await client.threads.delete(str(thread_id), headers=headers)
        raise


async def _run(args: argparse.Namespace) -> None:
    if args.ttl_seconds < 60 or args.ttl_seconds > 86_400:
        raise RuntimeError("--ttl-seconds must be between 60 and 86400")
    settings = get_settings()
    authorization = _authorization(settings)
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ProductAnalysisService(session_factory=session_factory)
    client = get_client(url=settings.agent_server_url)
    fixture = cast(FixtureKind, args.fixture)
    runner = AgentServerRunner(
        client=client,
        assistant_id=FIXTURE_ASSISTANTS[fixture],
    )
    try:
        await service.bootstrap_actor(FIXTURE_ACTOR)
        actor_ids = await _resolved_actor_ids(session_factory)
        results = []
        for index in range(args.count):
            results.append(
                await _seed_one(
                    client=client,
                    runner=runner,
                    session_factory=session_factory,
                    actor_ids=actor_ids,
                    authorization=authorization,
                    label=f"{args.label_prefix}-{index + 1}",
                    ttl_seconds=args.ttl_seconds,
                    fixture=fixture,
                )
            )
        print(json.dumps(results, sort_keys=True))
    finally:
        await engine.dispose()


def main() -> None:
    args = _parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
