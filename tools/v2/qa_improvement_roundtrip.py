"""Run a local PostgreSQL Postmortem and Frozen Replay round-trip."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.schemas import PostmortemSubmission
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import get_settings


def _actor() -> ActorContext:
    return ActorContext(
        tenant_id="dev-tenant",
        workspace_id="dev-workspace",
        user_id="dev-user",
        identity_issuer="crypto-alert-v2-compose",
        context_id=UUID("99999999-9999-4999-8999-999999999999"),
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


async def main() -> None:
    settings = get_settings()
    if settings.product_database_url is None:
        raise RuntimeError("PRODUCT_DATABASE_URL is not configured")
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ProductAnalysisService(session_factory=factory)
    actor = _actor()
    runs = await service.list_runs(actor, limit=100)
    source = next(
        (
            item
            for item in runs["items"]
            if item["status"] == "succeeded" and item.get("main_action") is not None
        ),
        None,
    )
    if source is None:
        raise RuntimeError("no succeeded run with a persisted decision is available")
    run_id = str(source["run_id"])
    case = await service.create_postmortem(
        actor,
        run_id,
        PostmortemSubmission(
            category="operator_postmortem",
            title="QA frozen replay round-trip",
            summary="Freeze the latest persisted decision without live provider access.",
            expected_behavior="RuleJudge reads only the persisted packet.",
            actual_behavior="The source Run already completed through Product admission.",
        ),
        f"qa-improvement-{run_id}",
    )
    if case is None:
        raise RuntimeError("source Run was not actor-visible")
    frozen = await service.freeze_postmortem(actor, str(case["id"]))
    replayed = await service.freeze_postmortem(actor, str(case["id"]))
    listed = await service.list_postmortems(actor, limit=100)
    if frozen is None or replayed is None:
        raise RuntimeError("Postmortem freeze unexpectedly disappeared")
    replay = frozen["frozen_replay"]
    replay_again = replayed["frozen_replay"]
    print(
        json.dumps(
            {
                "case_id": str(case["id"]),
                "status": frozen["status"],
                "listed": any(item["id"] == case["id"] for item in listed["items"]),
                "source_hash_present": bool(replay and replay["source_hash"]),
                "freeze_idempotent": bool(
                    replay
                    and replay_again
                    and replay["id"] == replay_again["id"]
                    and replay["source_hash"] == replay_again["source_hash"]
                ),
                "allow_live_fetch": replay["allow_live_fetch"] if replay else None,
                "allow_live_side_effects": (
                    replay["allow_live_side_effects"] if replay else None
                ),
                "rule_metrics": replay["rule_metrics"] if replay else None,
            },
            sort_keys=True,
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
