from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.integrations.webhook_signing import (
    WebhookSignature,
    WebhookSignatureError,
    WebhookSigner,
)
from crypto_alert_v2.persistence.models import (
    WebhookDeliveryAudit,
    WebhookIntegration,
    WebhookReplayNonce,
)
from crypto_alert_v2.persistence.repositories import ResolvedActor


@dataclass(frozen=True, slots=True)
class WebhookDeliveryResult:
    status: str
    reason: str | None
    audit_id: UUID
    payload_hash: str


class WebhookRepository:
    def __init__(self, session: AsyncSession, resolved: ResolvedActor) -> None:
        self.session = session
        self.resolved = resolved

    async def create_integration(
        self,
        *,
        name: str,
        active_key_id: str,
        accepted_key_ids: tuple[str, ...],
    ) -> WebhookIntegration:
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 120:
            raise ValueError("webhook integration name is invalid")
        accepted = tuple(dict.fromkeys((active_key_id, *accepted_key_ids)))
        integration = WebhookIntegration(
            id=uuid4(),
            tenant_id=self.resolved.tenant_id,
            workspace_id=self.resolved.workspace_id,
            owner_user_id=self.resolved.user_id,
            name=normalized_name,
            active=True,
            active_key_id=active_key_id,
            accepted_key_ids=list(accepted),
        )
        self.session.add(integration)
        await self.session.flush()
        return integration

    async def list_audits(
        self,
        integration_id: UUID,
        *,
        limit: int = 100,
    ) -> list[WebhookDeliveryAudit]:
        if limit < 1 or limit > 1000:
            raise ValueError("webhook audit limit is invalid")
        return list(
            (
                await self.session.scalars(
                    select(WebhookDeliveryAudit)
                    .where(
                        WebhookDeliveryAudit.tenant_id == self.resolved.tenant_id,
                        WebhookDeliveryAudit.workspace_id
                        == self.resolved.workspace_id,
                        WebhookDeliveryAudit.owner_user_id == self.resolved.user_id,
                        WebhookDeliveryAudit.integration_id == integration_id,
                    )
                    .order_by(
                        WebhookDeliveryAudit.received_at.desc(),
                        WebhookDeliveryAudit.id.desc(),
                    )
                    .limit(limit)
                )
            ).all()
        )


async def accept_webhook_delivery(
    session: AsyncSession,
    *,
    integration_id: UUID,
    payload: bytes,
    signature: WebhookSignature,
    signer: WebhookSigner,
    received_at: datetime,
    nonce_ttl_seconds: int = 600,
) -> WebhookDeliveryResult:
    if received_at.tzinfo is None:
        raise ValueError("webhook received_at must be timezone-aware")
    if nonce_ttl_seconds < 1 or nonce_ttl_seconds > 86_400:
        raise ValueError("webhook nonce TTL is invalid")
    integration = await session.scalar(
        select(WebhookIntegration)
        .where(WebhookIntegration.id == integration_id)
        .with_for_update()
    )
    if integration is None or not integration.active:
        raise LookupError("webhook integration is unavailable")
    nonce_hash = sha256(signature.nonce.encode("utf-8")).hexdigest()
    payload_hash = sha256(payload).hexdigest()
    reason = None
    try:
        if signature.key_id not in integration.accepted_key_ids:
            raise WebhookSignatureError(
                "unknown_key", "webhook signing key is unknown"
            )
        payload_hash = signer.verify(payload, signature)
    except WebhookSignatureError as exc:
        reason = exc.code
    except ValueError:
        reason = "signature_malformed"
    if reason is not None:
        audit = await _append_audit(
            session,
            integration=integration,
            signature=signature,
            nonce_hash=nonce_hash,
            payload_hash=payload_hash,
            status="rejected",
            reason=reason,
            received_at=received_at,
        )
        return WebhookDeliveryResult(
            status=audit.status,
            reason=audit.reason,
            audit_id=audit.id,
            payload_hash=payload_hash,
        )

    prior_event = await session.scalar(
        select(WebhookDeliveryAudit.id).where(
            WebhookDeliveryAudit.integration_id == integration.id,
            WebhookDeliveryAudit.event_id == signature.event_id,
            WebhookDeliveryAudit.status == "accepted",
        )
    )
    if prior_event is not None:
        audit = await _append_audit(
            session,
            integration=integration,
            signature=signature,
            nonce_hash=nonce_hash,
            payload_hash=payload_hash,
            status="replayed",
            reason="duplicate_event",
            received_at=received_at,
        )
        return WebhookDeliveryResult(
            status=audit.status,
            reason=audit.reason,
            audit_id=audit.id,
            payload_hash=payload_hash,
        )

    inserted_nonce = await session.scalar(
        insert(WebhookReplayNonce)
        .values(
            id=uuid4(),
            tenant_id=integration.tenant_id,
            workspace_id=integration.workspace_id,
            owner_user_id=integration.owner_user_id,
            integration_id=integration.id,
            nonce_hash=nonce_hash,
            expires_at=received_at + timedelta(seconds=nonce_ttl_seconds),
        )
        .on_conflict_do_nothing(
            index_elements=[
                WebhookReplayNonce.integration_id,
                WebhookReplayNonce.nonce_hash,
            ]
        )
        .returning(WebhookReplayNonce.id)
    )
    status = "accepted" if inserted_nonce is not None else "replayed"
    reason = None if inserted_nonce is not None else "nonce_replay"
    audit = await _append_audit(
        session,
        integration=integration,
        signature=signature,
        nonce_hash=nonce_hash,
        payload_hash=payload_hash,
        status=status,
        reason=reason,
        received_at=received_at,
    )
    return WebhookDeliveryResult(
        status=audit.status,
        reason=audit.reason,
        audit_id=audit.id,
        payload_hash=payload_hash,
    )


async def _append_audit(
    session: AsyncSession,
    *,
    integration: WebhookIntegration,
    signature: WebhookSignature,
    nonce_hash: str,
    payload_hash: str,
    status: str,
    reason: str | None,
    received_at: datetime,
) -> WebhookDeliveryAudit:
    audit = WebhookDeliveryAudit(
        id=uuid4(),
        tenant_id=integration.tenant_id,
        workspace_id=integration.workspace_id,
        owner_user_id=integration.owner_user_id,
        integration_id=integration.id,
        event_id=signature.event_id,
        key_id=signature.key_id,
        nonce_hash=nonce_hash,
        payload_hash=payload_hash,
        status=status,
        reason=reason,
        received_at=received_at,
    )
    session.add(audit)
    await session.flush()
    return audit


__all__ = [
    "WebhookDeliveryResult",
    "WebhookRepository",
    "accept_webhook_delivery",
]
