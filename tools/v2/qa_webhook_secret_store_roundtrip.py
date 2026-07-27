"""Exercise file-backed secrets and durable webhook replay protection."""

from __future__ import annotations

import asyncio
from base64 import urlsafe_b64encode
from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.integrations.secret_store import FileSecretStore
from crypto_alert_v2.integrations.webhook_repository import (
    WebhookRepository,
    accept_webhook_delivery,
)
from crypto_alert_v2.integrations.webhook_signing import WebhookSigner
from crypto_alert_v2.persistence.models import WebhookDeliveryAudit
from crypto_alert_v2.persistence.repositories import resolve_actor


def _key(byte: int) -> str:
    return urlsafe_b64encode(bytes([byte]) * 32).decode().rstrip("=")


async def main() -> None:
    settings = get_settings()
    if settings.product_database_url is None:
        raise RuntimeError("PRODUCT_DATABASE_URL is not configured")
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    actor = ActorContext(
        tenant_id="qa-webhook-tenant",
        workspace_id=f"qa-webhook-workspace-{uuid4().hex[:12]}",
        user_id="qa-webhook-user",
        identity_issuer="crypto-alert-v2-qa",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=factory)
    await service.bootstrap_actor(actor)
    now = datetime.now(UTC)
    secret_canary = "webhook-secret-canary-must-not-persist"
    with TemporaryDirectory(prefix="crypto-alert-webhook-") as directory:
        root = Path(directory)
        (root / "webhook_signing_v1").write_text(_key(1), encoding="utf-8")
        (root / "webhook_signing_v2").write_text(_key(2), encoding="utf-8")
        (root / "canary_secret").write_text(secret_canary, encoding="utf-8")
        store = FileSecretStore(root)
        old_signer = WebhookSigner(
            secret_store=store,
            active_key_id="v1",
            clock=lambda: now,
        )
        rotated_signer = WebhookSigner(
            secret_store=store,
            active_key_id="v2",
            accepted_key_ids=("v1",),
            clock=lambda: now,
        )
        async with factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            integration = await WebhookRepository(
                session, resolved
            ).create_integration(
                name="QA signed webhook",
                active_key_id="v2",
                accepted_key_ids=("v1",),
            )
            integration_id = integration.id

        payload = b'{"event":"task.completed"}'
        old_signature = old_signer.sign(
            payload,
            event_id="qa-event-old",
            nonce="ABCDEFGHIJKLMNOP",
        )
        active_signature = rotated_signer.sign(
            payload,
            event_id="qa-event-active",
            nonce="QRSTUVWXYZabcdef",
        )
        nonce_replay_signature = rotated_signer.sign(
            payload,
            event_id="qa-event-nonce-replay",
            nonce=active_signature.nonce,
        )
        async with factory() as session, session.begin():
            old_result = await accept_webhook_delivery(
                session,
                integration_id=integration_id,
                payload=payload,
                signature=old_signature,
                signer=rotated_signer,
                received_at=now,
            )
            active_result = await accept_webhook_delivery(
                session,
                integration_id=integration_id,
                payload=payload,
                signature=active_signature,
                signer=rotated_signer,
                received_at=now,
            )
            duplicate_result = await accept_webhook_delivery(
                session,
                integration_id=integration_id,
                payload=payload,
                signature=active_signature,
                signer=rotated_signer,
                received_at=now,
            )
            nonce_replay_result = await accept_webhook_delivery(
                session,
                integration_id=integration_id,
                payload=payload,
                signature=nonce_replay_signature,
                signer=rotated_signer,
                received_at=now,
            )
            tamper_result = await accept_webhook_delivery(
                session,
                integration_id=integration_id,
                payload=payload + b" ",
                signature=active_signature,
                signer=rotated_signer,
                received_at=now,
            )
        async with factory() as session:
            audits = list(
                (
                    await session.scalars(
                        select(WebhookDeliveryAudit)
                        .where(WebhookDeliveryAudit.integration_id == integration_id)
                        .order_by(WebhookDeliveryAudit.created_at)
                    )
                ).all()
            )
            serialized = json.dumps(
                [
                    {
                        "status": audit.status,
                        "reason": audit.reason,
                        "payload_hash": audit.payload_hash,
                        "nonce_hash": audit.nonce_hash,
                    }
                    for audit in audits
                ],
                sort_keys=True,
            )
            audit_id = audits[0].id
        mutation_blocked = False
        try:
            async with factory() as session, session.begin():
                await session.execute(
                    update(WebhookDeliveryAudit)
                    .where(WebhookDeliveryAudit.id == audit_id)
                    .values(status="rejected")
                )
        except DBAPIError:
            mutation_blocked = True

    print(
        json.dumps(
            {
                "old_key_status": old_result.status,
                "active_key_status": active_result.status,
                "duplicate_status": duplicate_result.status,
                "duplicate_reason": duplicate_result.reason,
                "nonce_replay_status": nonce_replay_result.status,
                "nonce_replay_reason": nonce_replay_result.reason,
                "tamper_status": tamper_result.status,
                "tamper_reason": tamper_result.reason,
                "audit_count": len(audits),
                "audit_mutation_blocked": mutation_blocked,
                "secret_canary_absent": secret_canary not in serialized,
            },
            sort_keys=True,
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
