from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.persistence.models import (
    DomainEvent,
    NotificationOutbox,
    Run,
    Task,
    Thread,
)
from crypto_alert_v2.domain.models import (
    EvidenceVerdict,
    MarketAnalysis,
    MarketSnapshot,
    RiskVerdict,
)
from crypto_alert_v2.domain.deep_research import DeepResearchArtifact
from crypto_alert_v2.providers.search import WebEvidence


TERMINAL_RUN_STATUSES = ("succeeded", "blocked", "failed", "cancelled")


@dataclass(frozen=True, slots=True)
class DomainEventSpec:
    event_type: str
    payload_ref: str
    payload_hash: str
    payload: dict[str, Any] | list[Any]
    schema_version: str = "1.0"


class DomainEventProjectionConflict(RuntimeError):
    """A replay reused a source identity for a different immutable payload."""


def _payload_hash(payload: object) -> str:
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _event_spec(event_type: str, payload_ref: str, payload: object) -> DomainEventSpec:
    return DomainEventSpec(
        event_type=event_type,
        payload_ref=payload_ref,
        payload_hash=_payload_hash(payload),
        payload=payload,  # type: ignore[arg-type]
    )


def progressive_event_specs(
    updates: dict[str, Any],
) -> tuple[DomainEventSpec, ...]:
    specs: list[DomainEventSpec] = []
    for node_name, raw_update in updates.items():
        if not isinstance(raw_update, dict):
            continue
        if node_name == "collect_market_snapshot":
            market = raw_update.get("market_snapshot")
            if isinstance(market, dict):
                payload = MarketSnapshot.model_validate(market).model_dump(
                    mode="json",
                    exclude_none=True,
                )
                specs.append(
                    _event_spec(
                        "market.snapshot.committed",
                        "official-update#/collect_market_snapshot/market_snapshot",
                        payload,
                    )
                )
            evidence = raw_update.get("web_evidence")
            if isinstance(evidence, list):
                payload = [
                    WebEvidence.model_validate(item).model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                    for item in evidence
                ]
                specs.append(
                    _event_spec(
                        "research.evidence.committed",
                        "official-update#/collect_market_snapshot/web_evidence",
                        payload,
                    )
                )
        elif node_name == "research_events":
            evidence = raw_update.get("web_evidence")
            if isinstance(evidence, list):
                payload = [
                    WebEvidence.model_validate(item).model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                    for item in evidence
                ]
                specs.append(
                    _event_spec(
                        "research.evidence.committed",
                        "official-update#/research_events/web_evidence",
                        payload,
                    )
                )
        elif node_name == "run_deep_research":
            evidence = raw_update.get("web_evidence")
            if isinstance(evidence, list):
                payload = [
                    WebEvidence.model_validate(item).model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                    for item in evidence
                ]
                specs.append(
                    _event_spec(
                        "research.evidence.committed",
                        "official-update#/run_deep_research/web_evidence",
                        payload,
                    )
                )
            artifact = raw_update.get("deep_research_artifact")
            if isinstance(artifact, dict):
                payload = DeepResearchArtifact.model_validate(artifact).model_dump(
                    mode="json",
                    exclude_none=True,
                )
                specs.append(
                    _event_spec(
                        "agent.output.committed",
                        "official-update#/run_deep_research/deep_research_artifact/report",
                        payload["report"],
                    )
                )
                if payload["status"] == "committed":
                    specs.append(
                        _event_spec(
                            "artifact.committed",
                            "official-update#/run_deep_research/deep_research_artifact",
                            payload,
                        )
                    )
        elif node_name == "analyze_market":
            analysis = raw_update.get("analysis")
            if isinstance(analysis, dict):
                payload = MarketAnalysis.model_validate(analysis).model_dump(
                    mode="json",
                    exclude_none=True,
                )
                specs.append(
                    _event_spec(
                        "agent.output.committed",
                        "official-update#/analyze_market/analysis",
                        payload,
                    )
                )
        elif node_name == "validate_evidence":
            verdict = raw_update.get("evidence_verdict")
            if isinstance(verdict, dict):
                payload = EvidenceVerdict.model_validate(verdict).model_dump(
                    mode="json",
                    exclude_none=True,
                )
                specs.append(
                    _event_spec(
                        "evidence.verdict.committed",
                        "official-update#/validate_evidence/evidence_verdict",
                        payload,
                    )
                )
        elif node_name == "apply_risk_policy":
            verdict = raw_update.get("risk_verdict")
            if isinstance(verdict, dict):
                payload = RiskVerdict.model_validate(verdict).model_dump(
                    mode="json",
                    exclude_none=True,
                )
                specs.append(
                    _event_spec(
                        "risk.verdict.committed",
                        "official-update#/apply_risk_policy/risk_verdict",
                        payload,
                    )
                )
    return tuple(specs)


def domain_event_specs(
    output: dict[str, Any],
    *,
    notification_payload: dict[str, Any] | None,
) -> tuple[DomainEventSpec, ...]:
    specs: list[DomainEventSpec] = []
    market = output.get("market_snapshot")
    evidence = output.get("web_evidence")
    artifact = output.get("artifact")
    deep_research_artifact = output.get("deep_research_artifact")
    if isinstance(market, dict):
        specs.append(
            _event_spec(
                "market.snapshot.committed",
                "output_payload#/market_snapshot",
                market,
            )
        )
    if isinstance(evidence, list) and (
        evidence
        or isinstance(artifact, dict)
        or isinstance(deep_research_artifact, dict)
    ):
        specs.append(
            _event_spec(
                "research.evidence.committed",
                "output_payload#/web_evidence",
                evidence,
            )
        )
    if isinstance(artifact, dict):
        for event_type, field in (
            ("agent.output.committed", "analysis"),
            ("evidence.verdict.committed", "evidence_verdict"),
            ("risk.verdict.committed", "risk_verdict"),
        ):
            payload = artifact.get(field)
            if isinstance(payload, dict):
                specs.append(
                    _event_spec(
                        event_type,
                        f"output_payload#/artifact/{field}",
                        payload,
                    )
                )
        if artifact.get("status") == "committed":
            specs.append(
                _event_spec(
                    "artifact.committed",
                    "output_payload#/artifact",
                    artifact,
                )
            )
    if isinstance(deep_research_artifact, dict):
        research_payload = DeepResearchArtifact.model_validate(
            deep_research_artifact
        ).model_dump(mode="json", exclude_none=True)
        specs.append(
            _event_spec(
                "agent.output.committed",
                "output_payload#/deep_research_artifact/report",
                research_payload["report"],
            )
        )
        if research_payload["status"] == "committed":
            specs.append(
                _event_spec(
                    "artifact.committed",
                    "output_payload#/deep_research_artifact",
                    research_payload,
                )
            )
    if notification_payload is not None:
        specs.append(
            _event_spec(
                "notification.planned",
                "notification_outbox#/payload",
                notification_payload,
            )
        )
    specs.append(_event_spec("run.terminal", "output_payload#", output))
    return tuple(specs)


async def append_domain_events(
    session: AsyncSession,
    *,
    task: Task,
    run: Run,
    output: dict[str, Any],
    notification_payload: dict[str, Any] | None,
    created_at: datetime,
) -> int:
    specs = domain_event_specs(
        output,
        notification_payload=notification_payload,
    )
    return await append_event_specs(
        session,
        task=task,
        run=run,
        specs=specs,
        source_event_key=f"terminal:{_payload_hash(output)}",
        source_event_id=None,
        checkpoint_id=run.checkpoint_id,
        created_at=created_at,
    )


async def append_progressive_events(
    session: AsyncSession,
    *,
    task: Task,
    run: Run,
    updates: dict[str, Any],
    source_event_id: str,
    checkpoint_id: str | None,
    created_at: datetime,
) -> int:
    if not source_event_id or len(source_event_id) > 255:
        raise ValueError("official stream event id must be between 1 and 255 chars")
    return await append_event_specs(
        session,
        task=task,
        run=run,
        specs=progressive_event_specs(updates),
        source_event_key=f"stream:{source_event_id}",
        source_event_id=source_event_id,
        checkpoint_id=checkpoint_id,
        created_at=created_at,
    )


async def append_event_specs(
    session: AsyncSession,
    *,
    task: Task,
    run: Run,
    specs: tuple[DomainEventSpec, ...],
    source_event_key: str,
    source_event_id: str | None,
    checkpoint_id: str | None,
    created_at: datetime,
) -> int:
    if not specs:
        return 0
    existing = list(
        (
            await session.scalars(
                select(DomainEvent)
                .where(DomainEvent.run_id == run.id)
                .order_by(DomainEvent.sequence)
            )
        ).all()
    )
    by_source_key = {event.source_event_key: event for event in existing}
    latest_by_type = {event.event_type: event for event in existing}
    pending: list[tuple[DomainEventSpec, str]] = []
    source_digest = sha256(source_event_key.encode("utf-8")).hexdigest()
    for spec in specs:
        stable_key = f"{source_digest}:{spec.event_type}"
        exact = by_source_key.get(stable_key)
        if exact is not None:
            if (
                exact.payload_hash != spec.payload_hash
                or _payload_hash(exact.payload) != spec.payload_hash
            ):
                raise DomainEventProjectionConflict(
                    "official event replay changed its immutable payload"
                )
            continue
        latest = latest_by_type.get(spec.event_type)
        if latest is not None and latest.payload_hash == spec.payload_hash:
            if _payload_hash(latest.payload) != spec.payload_hash:
                raise DomainEventProjectionConflict(
                    "persisted domain event payload does not match its hash"
                )
            continue
        pending.append((spec, stable_key))
    if not pending:
        return 0

    next_sequence = await session.scalar(
        update(Thread)
        .where(Thread.id == task.thread_id)
        .values(
            next_domain_event_sequence=(
                Thread.next_domain_event_sequence + len(pending)
            )
        )
        .returning(Thread.next_domain_event_sequence)
    )
    if next_sequence is None:
        raise RuntimeError("Domain Event Thread no longer exists")
    sequence = int(next_sequence) - len(pending)
    for spec, stable_key in pending:
        event_id = uuid4()
        session.add(
            DomainEvent(
                id=event_id,
                tenant_id=task.tenant_id,
                workspace_id=task.workspace_id,
                owner_user_id=task.owner_user_id,
                thread_id=task.thread_id,
                task_id=task.id,
                run_id=run.id,
                official_run_id=run.official_run_id,
                checkpoint_id=checkpoint_id,
                event_type=spec.event_type,
                source_event_key=stable_key,
                source_event_id=source_event_id,
                schema_version=spec.schema_version,
                payload_ref=f"domain-event://{event_id}/payload",
                payload_hash=spec.payload_hash,
                payload=spec.payload,
                sequence=sequence,
                created_at=created_at,
            )
        )
        sequence += 1
    return len(pending)


class DomainEventProjectionWorker:
    def __init__(self, *, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def dispatch_once(self, *, run_id: UUID | None = None) -> bool:
        async with self._session_factory() as session, session.begin():

            def missing(event_type: str) -> Any:
                return ~exists(
                    select(DomainEvent.id).where(
                        DomainEvent.run_id == Run.id,
                        DomainEvent.event_type == event_type,
                    )
                )

            query = (
                select(Run, Task)
                .join(Task, Task.id == Run.task_id)
                .where(
                    Run.status.in_(TERMINAL_RUN_STATUSES),
                    Run.output_payload.is_not(None),
                    or_(
                        missing("run.terminal"),
                        and_(
                            Run.output_payload["market_snapshot"].is_not(None),
                            missing("market.snapshot.committed"),
                        ),
                        and_(
                            or_(
                                Run.output_payload["artifact"].is_not(None),
                                Run.output_payload["web_evidence"].is_not(None),
                            ),
                            missing("research.evidence.committed"),
                        ),
                        and_(
                            Run.output_payload["artifact"]["analysis"].is_not(None),
                            missing("agent.output.committed"),
                        ),
                        and_(
                            Run.output_payload["artifact"]["evidence_verdict"].is_not(
                                None
                            ),
                            missing("evidence.verdict.committed"),
                        ),
                        and_(
                            Run.output_payload["artifact"]["risk_verdict"].is_not(None),
                            missing("risk.verdict.committed"),
                        ),
                        and_(
                            Run.output_payload["artifact"]["status"].astext
                            == "committed",
                            missing("artifact.committed"),
                        ),
                        and_(
                            exists(
                                select(NotificationOutbox.id).where(
                                    NotificationOutbox.run_id == Run.id
                                )
                            ),
                            missing("notification.planned"),
                        ),
                    ),
                )
                .order_by(Run.finished_at, Run.id)
                .limit(1)
                .with_for_update(of=Run, skip_locked=True)
            )
            if run_id is not None:
                query = query.where(Run.id == run_id)
            row = (await session.execute(query)).one_or_none()
            if row is None:
                return False
            run, task = row
            notification_payload = await session.scalar(
                select(NotificationOutbox.payload)
                .where(NotificationOutbox.run_id == run.id)
                .order_by(NotificationOutbox.created_at.desc())
                .limit(1)
            )
            output = run.output_payload
            if not isinstance(output, dict):
                return False
            await append_domain_events(
                session,
                task=task,
                run=run,
                output=output,
                notification_payload=(
                    notification_payload
                    if isinstance(notification_payload, dict)
                    else None
                ),
                created_at=run.finished_at or datetime.now(UTC),
            )
            return True

    async def release_owned_leases(self) -> None:
        return None


__all__ = [
    "DomainEventProjectionConflict",
    "DomainEventProjectionWorker",
    "DomainEventSpec",
    "append_domain_events",
    "append_event_specs",
    "append_progressive_events",
    "domain_event_specs",
    "progressive_event_specs",
]
