from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.persistence.models import (
    ImprovementReview,
    MonitorTrigger,
    Run,
    Task,
    UsageLedgerEntry,
    UsageReconciliation,
    WorkspaceEntitlement,
)
from crypto_alert_v2.persistence.repositories import ResolvedActor


USAGE_UNITS = (
    "agent_admission",
    "trigger",
    "model_token",
    "search_request",
    "runtime_millisecond",
    "storage_byte",
)

_LIMIT_FIELD_BY_UNIT = {
    "agent_admission": "monthly_agent_admission_limit",
    "trigger": "monthly_trigger_limit",
    "model_token": "monthly_model_token_limit",
    "search_request": "monthly_search_request_limit",
    "runtime_millisecond": "monthly_runtime_millisecond_limit",
    "storage_byte": "storage_byte_limit",
}


class UsageGovernanceError(RuntimeError):
    code = "usage_governance_error"


class UsageEntitlementDenied(UsageGovernanceError):
    code = "entitlement_unavailable"


class UsageModeDenied(UsageGovernanceError):
    code = "task_mode_not_entitled"


class UsageQuotaExceeded(UsageGovernanceError):
    code = "quota_exceeded"

    def __init__(self, *, unit: str, current: int, limit: int) -> None:
        self.unit = unit
        self.current = current
        self.limit = limit
        super().__init__(f"{unit} quota exceeded ({current}/{limit})")


@dataclass(frozen=True, slots=True)
class UsageFact:
    idempotency_key: str
    owner_user_id: UUID
    operation_type: str
    resource_type: str
    resource_id: str
    unit: str
    quantity: int
    source_receipt_hash: str
    metadata: dict[str, Any]


def usage_period_start(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("usage timestamp must be timezone-aware")
    normalized = value.astimezone(UTC)
    return normalized.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(value: datetime) -> datetime:
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1)
    return value.replace(month=value.month + 1)


def _canonical_hash(value: Any) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _model_tokens(payload: dict[str, Any] | None) -> int:
    if payload is None:
        return 0
    total = 0
    seen_lists: set[int] = set()

    def visit(value: Any) -> None:
        nonlocal total
        if isinstance(value, dict):
            audits = value.get("model_audits")
            if isinstance(audits, list) and id(audits) not in seen_lists:
                seen_lists.add(id(audits))
                for audit in audits:
                    if not isinstance(audit, dict):
                        continue
                    tokens = audit.get("total_tokens")
                    if isinstance(tokens, int) and not isinstance(tokens, bool):
                        total += max(tokens, 0)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return total


def _search_requests(payload: dict[str, Any] | None) -> int:
    if payload is None:
        return 0
    evidence = payload.get("web_evidence")
    queries = {
        str(item.get("query")).strip()
        for item in evidence
        if isinstance(item, dict) and str(item.get("query") or "").strip()
    } if isinstance(evidence, list) else set()
    attempted = 0

    def visit(value: Any) -> None:
        nonlocal attempted
        if isinstance(value, dict):
            coverage = value.get("search_coverage")
            if isinstance(coverage, dict):
                count = coverage.get("attempted_queries")
                if isinstance(count, int) and not isinstance(count, bool):
                    attempted = max(attempted, max(count, 0))
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return max(len(queries), attempted)


def run_usage_facts(run: Run) -> list[UsageFact]:
    if run.finished_at is None or run.output_payload is None:
        return []
    output_hash = run.terminal_output_hash or _canonical_hash(run.output_payload)
    quantities = {
        "model_token": _model_tokens(run.output_payload),
        "search_request": _search_requests(run.output_payload),
        "runtime_millisecond": (
            max(1, int((run.finished_at - run.started_at).total_seconds() * 1000))
            if run.started_at is not None
            else 0
        ),
        "storage_byte": len(
            json.dumps(
                run.output_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ),
    }
    return [
        UsageFact(
            idempotency_key=f"run-usage:{run.id}:{unit}",
            owner_user_id=run.owner_user_id,
            operation_type="agent_run",
            resource_type="run",
            resource_id=str(run.id),
            unit=unit,
            quantity=quantity,
            source_receipt_hash=output_hash,
            metadata={"task_id": str(run.task_id), "attempt": run.attempt},
        )
        for unit, quantity in quantities.items()
        if quantity > 0
    ]


async def append_run_usage_receipts(
    session: AsyncSession,
    *,
    task: Task,
    run: Run,
) -> None:
    entitlement = await session.scalar(
        select(WorkspaceEntitlement).where(
            WorkspaceEntitlement.tenant_id == task.tenant_id,
            WorkspaceEntitlement.workspace_id == task.workspace_id,
        )
    )
    if entitlement is None:
        raise UsageEntitlementDenied(
            "terminal usage cannot be recorded without a workspace entitlement"
        )
    repository = UsageGovernanceRepository(
        session,
        ResolvedActor(
            tenant_id=task.tenant_id,
            workspace_id=task.workspace_id,
            user_id=task.owner_user_id,
            membership_id=UUID(int=0),
            role="usage-recorder",
            permissions=(),
        ),
    )
    period_start = usage_period_start(run.finished_at or datetime.now(UTC))
    for fact in run_usage_facts(run):
        await repository.append_fact(
            fact,
            entitlement_id=entitlement.id,
            period_start=period_start,
        )


class UsageGovernanceRepository:
    def __init__(self, session: AsyncSession, resolved: ResolvedActor) -> None:
        self.session = session
        self.resolved = resolved

    async def require_entitlement(
        self, *, now: datetime, lock: bool = False
    ) -> WorkspaceEntitlement:
        statement = select(WorkspaceEntitlement).where(
            WorkspaceEntitlement.tenant_id == self.resolved.tenant_id,
            WorkspaceEntitlement.workspace_id == self.resolved.workspace_id,
        )
        if lock:
            statement = statement.with_for_update()
        entitlement = await self.session.scalar(statement)
        if (
            entitlement is None
            or not entitlement.active
            or entitlement.valid_from > now
            or (
                entitlement.valid_until is not None
                and entitlement.valid_until <= now
            )
        ):
            raise UsageEntitlementDenied("workspace entitlement is unavailable")
        return entitlement

    async def total(self, *, unit: str, period_start: datetime) -> int:
        if unit not in USAGE_UNITS:
            raise ValueError("unsupported usage unit")
        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(UsageLedgerEntry.quantity), 0)).where(
                    UsageLedgerEntry.tenant_id == self.resolved.tenant_id,
                    UsageLedgerEntry.workspace_id == self.resolved.workspace_id,
                    UsageLedgerEntry.period_start == period_start,
                    UsageLedgerEntry.unit == unit,
                )
            )
            or 0
        )

    async def append_fact(
        self,
        fact: UsageFact,
        *,
        entitlement_id: UUID,
        period_start: datetime,
    ) -> UsageLedgerEntry:
        statement = (
            insert(UsageLedgerEntry)
            .values(
                id=uuid4(),
                tenant_id=self.resolved.tenant_id,
                workspace_id=self.resolved.workspace_id,
                owner_user_id=fact.owner_user_id,
                entitlement_id=entitlement_id,
                period_start=period_start,
                quantity=fact.quantity,
                unit=fact.unit,
                operation_type=fact.operation_type,
                resource_type=fact.resource_type,
                resource_id=fact.resource_id,
                source_receipt_hash=fact.source_receipt_hash,
                idempotency_key=fact.idempotency_key,
                ledger_metadata=fact.metadata,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    UsageLedgerEntry.tenant_id,
                    UsageLedgerEntry.workspace_id,
                    UsageLedgerEntry.idempotency_key,
                ]
            )
            .returning(UsageLedgerEntry.id)
        )
        inserted_id = await self.session.scalar(statement)
        if inserted_id is None:
            existing = await self.session.scalar(
                select(UsageLedgerEntry).where(
                    UsageLedgerEntry.tenant_id == self.resolved.tenant_id,
                    UsageLedgerEntry.workspace_id == self.resolved.workspace_id,
                    UsageLedgerEntry.idempotency_key == fact.idempotency_key,
                )
            )
            if existing is None:
                raise RuntimeError("usage receipt disappeared after idempotent insert")
            return existing
        receipt = await self.session.scalar(
            select(UsageLedgerEntry).where(UsageLedgerEntry.id == inserted_id)
        )
        if receipt is None:
            raise RuntimeError("usage receipt was not persisted")
        return receipt

    async def admit_agent(
        self,
        *,
        task_type: str,
        resource_type: str,
        resource_id: str,
        idempotency_key: str,
        now: datetime,
        owner_user_id: UUID | None = None,
    ) -> UsageLedgerEntry:
        entitlement = await self.require_entitlement(now=now, lock=True)
        if task_type not in entitlement.allowed_task_types:
            raise UsageModeDenied(f"task mode is not entitled: {task_type}")
        active_tasks = int(
            await self.session.scalar(
                select(func.count(Task.id)).where(
                    Task.tenant_id == self.resolved.tenant_id,
                    Task.workspace_id == self.resolved.workspace_id,
                    Task.status.in_(("queued", "running", "waiting_human")),
                )
            )
            or 0
        )
        pending_reviews = int(
            await self.session.scalar(
                select(func.count(ImprovementReview.id)).where(
                    ImprovementReview.tenant_id == self.resolved.tenant_id,
                    ImprovementReview.workspace_id == self.resolved.workspace_id,
                    ImprovementReview.status == "pending",
                )
            )
            or 0
        )
        active_operations = active_tasks + pending_reviews
        if active_operations >= entitlement.max_concurrent_tasks:
            raise UsageQuotaExceeded(
                unit="concurrent_agent_operation",
                current=active_operations,
                limit=entitlement.max_concurrent_tasks,
            )
        period_start = usage_period_start(now)
        current = await self.total(unit="agent_admission", period_start=period_start)
        if current >= entitlement.monthly_agent_admission_limit:
            raise UsageQuotaExceeded(
                unit="agent_admission",
                current=current,
                limit=entitlement.monthly_agent_admission_limit,
            )
        return await self.append_fact(
            UsageFact(
                idempotency_key=idempotency_key,
                owner_user_id=owner_user_id or self.resolved.user_id,
                operation_type=task_type,
                resource_type=resource_type,
                resource_id=resource_id,
                unit="agent_admission",
                quantity=1,
                source_receipt_hash=_canonical_hash(
                    {
                        "task_type": task_type,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                    }
                ),
                metadata={"task_type": task_type},
            ),
            entitlement_id=entitlement.id,
            period_start=period_start,
        )

    async def current_totals(self, *, period_start: datetime) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(
                    UsageLedgerEntry.unit,
                    func.coalesce(func.sum(UsageLedgerEntry.quantity), 0),
                )
                .where(
                    UsageLedgerEntry.tenant_id == self.resolved.tenant_id,
                    UsageLedgerEntry.workspace_id == self.resolved.workspace_id,
                    UsageLedgerEntry.period_start == period_start,
                )
                .group_by(UsageLedgerEntry.unit)
            )
        ).all()
        return {unit: int(quantity) for unit, quantity in rows}

    async def source_facts(self, *, period_start: datetime) -> list[UsageFact]:
        period_end = _next_month(period_start)
        tasks = list(
            (
                await self.session.scalars(
                    select(Task).where(
                        Task.tenant_id == self.resolved.tenant_id,
                        Task.workspace_id == self.resolved.workspace_id,
                        Task.created_at >= period_start,
                        Task.created_at < period_end,
                    )
                )
            ).all()
        )
        reviews = list(
            (
                await self.session.scalars(
                    select(ImprovementReview).where(
                        ImprovementReview.tenant_id == self.resolved.tenant_id,
                        ImprovementReview.workspace_id == self.resolved.workspace_id,
                        ImprovementReview.created_at >= period_start,
                        ImprovementReview.created_at < period_end,
                    )
                )
            ).all()
        )
        triggers = list(
            (
                await self.session.scalars(
                    select(MonitorTrigger).where(
                        MonitorTrigger.tenant_id == self.resolved.tenant_id,
                        MonitorTrigger.workspace_id == self.resolved.workspace_id,
                        MonitorTrigger.received_at >= period_start,
                        MonitorTrigger.received_at < period_end,
                    )
                )
            ).all()
        )
        runs = list(
            (
                await self.session.scalars(
                    select(Run).where(
                        Run.tenant_id == self.resolved.tenant_id,
                        Run.workspace_id == self.resolved.workspace_id,
                        Run.finished_at >= period_start,
                        Run.finished_at < period_end,
                    )
                )
            ).all()
        )
        facts: list[UsageFact] = []
        for task in tasks:
            facts.append(
                UsageFact(
                    idempotency_key=f"agent-admission:{task.id}",
                    owner_user_id=task.owner_user_id,
                    operation_type=task.task_type,
                    resource_type="task",
                    resource_id=str(task.id),
                    unit="agent_admission",
                    quantity=1,
                    source_receipt_hash=_canonical_hash(
                        {"task_id": str(task.id), "task_type": task.task_type}
                    ),
                    metadata={"task_type": task.task_type},
                )
            )
        for review in reviews:
            facts.append(
                UsageFact(
                    idempotency_key=f"candidate-review-admission:{review.id}",
                    owner_user_id=review.owner_user_id,
                    operation_type="candidate_review",
                    resource_type="improvement_review",
                    resource_id=str(review.id),
                    unit="agent_admission",
                    quantity=1,
                    source_receipt_hash=_canonical_hash(
                        {"review_id": str(review.id), "candidate_id": str(review.candidate_id)}
                    ),
                    metadata={"candidate_id": str(review.candidate_id)},
                )
            )
        for trigger in triggers:
            facts.append(
                UsageFact(
                    idempotency_key=f"reconcile-monitor-trigger:{trigger.id}",
                    owner_user_id=trigger.owner_user_id,
                    operation_type="monitor_trigger",
                    resource_type="monitor_trigger",
                    resource_id=str(trigger.id),
                    unit="trigger",
                    quantity=1,
                    source_receipt_hash=_canonical_hash(
                        {"trigger_id": str(trigger.id), "kind": trigger.kind}
                    ),
                    metadata={"monitor_id": str(trigger.monitor_id)},
                )
            )
        for run in runs:
            facts.extend(run_usage_facts(run))
        return sorted(facts, key=lambda fact: (fact.unit, fact.idempotency_key))

    async def reconcile(
        self,
        *,
        period_start: datetime,
        repair: bool,
        now: datetime,
    ) -> UsageReconciliation:
        entitlement = await self.require_entitlement(now=now, lock=repair)
        facts = await self.source_facts(period_start=period_start)
        if repair:
            existing_keys = set(
                (
                    await self.session.scalars(
                        select(UsageLedgerEntry.idempotency_key).where(
                            UsageLedgerEntry.tenant_id == self.resolved.tenant_id,
                            UsageLedgerEntry.workspace_id == self.resolved.workspace_id,
                            UsageLedgerEntry.period_start == period_start,
                        )
                    )
                ).all()
            )
            existing_trigger_ids = set(
                str(value)
                for value in (
                    await self.session.scalars(
                        select(UsageLedgerEntry.trigger_id).where(
                            UsageLedgerEntry.tenant_id == self.resolved.tenant_id,
                            UsageLedgerEntry.workspace_id == self.resolved.workspace_id,
                            UsageLedgerEntry.period_start == period_start,
                            UsageLedgerEntry.trigger_id.is_not(None),
                        )
                    )
                ).all()
                if value is not None
            )
            for fact in facts:
                if fact.idempotency_key in existing_keys:
                    continue
                if (
                    fact.resource_type == "monitor_trigger"
                    and fact.resource_id in existing_trigger_ids
                ):
                    continue
                await self.append_fact(
                    fact,
                    entitlement_id=entitlement.id,
                    period_start=period_start,
                )
        source_totals = {unit: 0 for unit in USAGE_UNITS}
        for fact in facts:
            source_totals[fact.unit] += fact.quantity
        ledger_totals = {unit: 0 for unit in USAGE_UNITS}
        ledger_totals.update(await self.current_totals(period_start=period_start))
        discrepancies = {
            unit: {
                "source": source_totals[unit],
                "ledger": ledger_totals[unit],
                "delta": ledger_totals[unit] - source_totals[unit],
            }
            for unit in USAGE_UNITS
            if source_totals[unit] != ledger_totals[unit]
        }
        source_hash = _canonical_hash(
            [
                {
                    "idempotency_key": fact.idempotency_key,
                    "unit": fact.unit,
                    "quantity": fact.quantity,
                    "source_receipt_hash": fact.source_receipt_hash,
                }
                for fact in facts
            ]
        )
        ledger_hash = _canonical_hash(ledger_totals)
        statement = (
            insert(UsageReconciliation)
            .values(
                id=uuid4(),
                tenant_id=self.resolved.tenant_id,
                workspace_id=self.resolved.workspace_id,
                owner_user_id=self.resolved.user_id,
                period_start=period_start,
                status="discrepant" if discrepancies else "reconciled",
                source_totals=source_totals,
                ledger_totals=ledger_totals,
                discrepancies=discrepancies,
                source_hash=source_hash,
                ledger_hash=ledger_hash,
                repair_applied=repair,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    UsageReconciliation.tenant_id,
                    UsageReconciliation.workspace_id,
                    UsageReconciliation.period_start,
                    UsageReconciliation.source_hash,
                    UsageReconciliation.ledger_hash,
                ]
            )
            .returning(UsageReconciliation.id)
        )
        reconciliation_id = await self.session.scalar(statement)
        if reconciliation_id is None:
            reconciliation = await self.session.scalar(
                select(UsageReconciliation).where(
                    UsageReconciliation.tenant_id == self.resolved.tenant_id,
                    UsageReconciliation.workspace_id == self.resolved.workspace_id,
                    UsageReconciliation.period_start == period_start,
                    UsageReconciliation.source_hash == source_hash,
                    UsageReconciliation.ledger_hash == ledger_hash,
                )
            )
        else:
            reconciliation = await self.session.scalar(
                select(UsageReconciliation).where(
                    UsageReconciliation.id == reconciliation_id
                )
            )
        if reconciliation is None:
            raise RuntimeError("usage reconciliation receipt was not persisted")
        return reconciliation


def entitlement_limits(entitlement: WorkspaceEntitlement) -> dict[str, int]:
    return {
        unit: int(getattr(entitlement, field))
        for unit, field in _LIMIT_FIELD_BY_UNIT.items()
    }


def reconciliation_view(receipt: UsageReconciliation) -> dict[str, Any]:
    return {
        "id": receipt.id,
        "period_start": receipt.period_start,
        "status": receipt.status,
        "source_totals": receipt.source_totals,
        "ledger_totals": receipt.ledger_totals,
        "discrepancies": receipt.discrepancies,
        "source_hash": receipt.source_hash,
        "ledger_hash": receipt.ledger_hash,
        "repair_applied": receipt.repair_applied,
        "created_at": receipt.created_at,
    }


__all__ = [
    "USAGE_UNITS",
    "UsageEntitlementDenied",
    "UsageGovernanceError",
    "UsageGovernanceRepository",
    "UsageModeDenied",
    "UsageQuotaExceeded",
    "append_run_usage_receipts",
    "entitlement_limits",
    "reconciliation_view",
    "run_usage_facts",
    "usage_period_start",
]
