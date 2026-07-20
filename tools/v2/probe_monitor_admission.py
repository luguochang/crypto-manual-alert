"""Read-only PostgreSQL probe for the scheduled Monitor admission boundary."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("PRODUCT_DATABASE_URL"))
    parser.add_argument("--monitor-id")
    parser.add_argument("--since-minutes", type=int, default=15)
    return parser


async def _probe(
    database_url: str,
    *,
    monitor_id: str | None,
    since_minutes: int,
) -> dict[str, Any]:
    if since_minutes < 1:
        raise ValueError("--since-minutes must be positive")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            params: dict[str, Any] = {"since_minutes": since_minutes}
            monitor_filter = ""
            if monitor_id is not None:
                monitor_filter = "and monitor_id = :monitor_id"
                params["monitor_id"] = monitor_id

            trigger_rows = (
                await connection.execute(
                    text(
                        f"""
                        select id, monitor_id, status, reason, task_id,
                               official_cron_id, official_run_id,
                               official_thread_id, received_at, admitted_at
                        from app.monitor_triggers
                        where kind = 'cron'
                          {monitor_filter}
                          and received_at >= now() - make_interval(mins => :since_minutes)
                        order by received_at desc
                        """
                    ),
                    params,
                )
            ).mappings().all()

            task_rows = (
                await connection.execute(
                    text(
                        """
                        select id, task_type, status, thread_id, created_at,
                               completed_at
                        from app.tasks
                        where task_type = 'monitor_ingress'
                          and created_at >= now() - make_interval(mins => :since_minutes)
                        order by created_at desc
                        """
                    ),
                    {"since_minutes": since_minutes},
                )
            ).mappings().all()

            command_rows = (
                await connection.execute(
                    text(
                        """
                        select id, task_id, command_type, status, official_run_id,
                               created_at, updated_at
                        from app.task_commands
                        where command_type = 'submit'
                          and created_at >= now() - make_interval(mins => :since_minutes)
                        order by created_at desc
                        """
                    ),
                    {"since_minutes": since_minutes},
                )
            ).mappings().all()

            run_rows = (
                await connection.execute(
                    text(
                        """
                        select r.id, r.task_id, r.status, r.official_run_id,
                               r.created_at, t.task_type
                        from app.runs r
                        join app.tasks t on t.id = r.task_id
                        where r.created_at >= now() - make_interval(mins => :since_minutes)
                        order by r.created_at desc
                        """
                    ),
                    {"since_minutes": since_minutes},
                )
            ).mappings().all()

            artifact_rows = (
                await connection.execute(
                    text(
                        """
                        select a.id, a.task_id, a.artifact_type, a.created_at
                        from app.artifacts a
                        where a.created_at >= now() - make_interval(mins => :since_minutes)
                        order by a.created_at desc
                        """
                    ),
                    {"since_minutes": since_minutes},
                )
            ).mappings().all()

            task_detail_rows = (
                await connection.execute(
                    text(
                        f"""
                        select t.id, t.status,
                               coalesce((
                                   select json_agg(json_build_object(
                                       'id', r.id,
                                       'status', r.status,
                                       'official_run_id', r.official_run_id
                                   ) order by r.created_at)
                                   from app.runs r
                                   where r.task_id = t.id
                               ), '[]'::json) as runs,
                               (select count(*) from app.market_snapshots ms
                                where ms.task_id = t.id) as market_snapshots,
                               (select count(*) from app.web_evidence we
                                where we.task_id = t.id) as web_evidence,
                               (select count(*) from app.artifact_versions av
                                where av.task_id = t.id) as artifact_versions,
                               (select count(*) from app.decisions d
                                where d.task_id = t.id) as decisions,
                               (select count(*) from app.domain_events de
                                where de.task_id = t.id) as domain_events
                        from app.tasks t
                        where t.id in (
                            select task_id
                            from app.monitor_triggers
                            where kind = 'cron'
                              {monitor_filter}
                              and task_id is not null
                              and received_at >= now() - make_interval(mins => :since_minutes)
                        )
                        order by t.created_at desc
                        """
                    ),
                    params,
                )
            ).mappings().all()

            committed_artifact_rows = (
                await connection.execute(
                    text(
                        """
                        select a.id as artifact_id,
                               av.id as artifact_version_id,
                               av.version_number,
                               av.status,
                               t.external_id as tenant,
                               w.external_id as workspace,
                               u.external_subject as owner
                        from app.artifacts a
                        join app.artifact_versions av
                          on av.artifact_id = a.id
                         and av.version_number = a.latest_version_number
                        join app.tenants t on t.id = a.tenant_id
                        join app.workspaces w on w.id = a.workspace_id
                        join app.users u on u.id = a.owner_user_id
                        where av.status = 'committed'
                        order by av.created_at desc
                        limit 20
                        """
                    )
                )
            ).mappings().all()

            return {
                "since_minutes": since_minutes,
                "monitor_id": monitor_id,
                "cron_triggers": [dict(row) for row in trigger_rows],
                "monitor_ingress_tasks": [dict(row) for row in task_rows],
                "submit_commands": [dict(row) for row in command_rows],
                "product_runs": [dict(row) for row in run_rows],
                "artifacts": [dict(row) for row in artifact_rows],
                "monitor_task_details": [dict(row) for row in task_detail_rows],
                "committed_artifacts": [dict(row) for row in committed_artifact_rows],
            }
    finally:
        await engine.dispose()


def main() -> None:
    args = _parser().parse_args()
    if not args.database_url:
        raise SystemExit("--database-url or PRODUCT_DATABASE_URL is required")
    result = asyncio.run(
        _probe(
            args.database_url,
            monitor_id=args.monitor_id,
            since_minutes=args.since_minutes,
        )
    )
    print(json.dumps(result, default=str, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
