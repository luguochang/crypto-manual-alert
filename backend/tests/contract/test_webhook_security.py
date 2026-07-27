from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import importlib.util
from io import StringIO
import os
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import SecretStr
import pytest

from crypto_alert_v2.integrations.secret_store import (
    EnvironmentSecretStore,
    FileSecretStore,
    integration_secret_store_from_environment,
)
from crypto_alert_v2.integrations.webhook_signing import (
    WebhookSignatureError,
    WebhookSigner,
)
from crypto_alert_v2.persistence.models import WebhookDeliveryAudit


NOW = datetime(2026, 7, 23, 15, 0, tzinfo=UTC)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _encoded_key(byte: int) -> str:
    return urlsafe_b64encode(bytes([byte]) * 32).decode().rstrip("=")


def _load_revision() -> Any:
    path = BACKEND_ROOT / "alembic" / "versions" / "0029_webhook_security.py"
    spec = importlib.util.spec_from_file_location("webhook_security", path)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _upgrade_sql() -> str:
    revision = _load_revision()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    revision.upgrade()
    return output.getvalue()


def test_file_secret_store_rejects_traversal_symlink_and_non_utf8(
    tmp_path: Path,
) -> None:
    (tmp_path / "notification_credential_key").write_text(
        _encoded_key(1), encoding="utf-8"
    )
    store = FileSecretStore(tmp_path)

    secret = store.get_secret("notification_credential_key")

    assert isinstance(secret, SecretStr)
    assert "AQEB" not in repr(secret)
    with pytest.raises(ValueError, match="name is invalid"):
        store.get_secret("../outside")
    if os.name != "nt":
        (tmp_path / "linked_secret").symlink_to(
            tmp_path / "notification_credential_key"
        )
        with pytest.raises(ValueError, match="non-symlink"):
            store.get_secret("linked_secret")
    (tmp_path / "binary_secret").write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="UTF-8"):
        store.get_secret("binary_secret")


def test_production_rejects_environment_secret_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTEGRATION_SECRET_STORE", "environment")
    with pytest.raises(ValueError, match="forbidden"):
        integration_secret_store_from_environment(app_environment="production")


def test_webhook_signature_detects_tamper_stale_nonce_and_supports_rotation() -> None:
    variables = {
        "WEBHOOK_SIGNING_V1": _encoded_key(1),
        "WEBHOOK_SIGNING_V2": _encoded_key(2),
    }
    old = WebhookSigner(
        secret_store=EnvironmentSecretStore(variables),
        active_key_id="v1",
        clock=lambda: NOW,
    )
    rotated = WebhookSigner(
        secret_store=EnvironmentSecretStore(variables),
        active_key_id="v2",
        accepted_key_ids=("v1",),
        clock=lambda: NOW,
    )
    payload = b'{"event":"task.completed"}'
    old_signature = old.sign(
        payload,
        event_id="evt-1",
        nonce="abcdefghijklmnop",
    )
    active_signature = rotated.sign(
        payload,
        event_id="evt-2",
        nonce="qrstuvwxyzABCDEF",
    )

    assert rotated.verify(payload, old_signature)
    assert rotated.verify(payload, active_signature)
    with pytest.raises(WebhookSignatureError, match="invalid") as tampered:
        rotated.verify(payload + b" ", active_signature)
    assert tampered.value.code == "signature_invalid"
    stale = replace(
        old_signature,
        timestamp=int((NOW - timedelta(minutes=6)).timestamp()),
    )
    with pytest.raises(WebhookSignatureError, match="stale") as stale_error:
        rotated.verify(payload, stale)
    assert stale_error.value.code == "stale_timestamp"
    with pytest.raises(ValueError, match="nonce"):
        rotated.sign(payload, event_id="evt-3", nonce="short")


def test_webhook_headers_never_include_secret_material() -> None:
    key = _encoded_key(3)
    signer = WebhookSigner(
        secret_store=EnvironmentSecretStore({"WEBHOOK_SIGNING_V1": key}),
        active_key_id="v1",
        clock=lambda: NOW,
    )
    headers = signer.sign(
        b"payload",
        event_id="evt-header-1",
        nonce="ABCDEFGHIJKLMNOP",
    ).headers()

    assert key not in repr(headers)
    assert set(headers) == {
        "X-Webhook-Key-Id",
        "X-Webhook-Timestamp",
        "X-Webhook-Nonce",
        "X-Webhook-Event-Id",
        "X-Webhook-Signature",
    }


def test_webhook_migration_has_nonce_uniqueness_and_append_only_audit() -> None:
    revision = _load_revision()
    sql = _upgrade_sql()

    assert revision.revision == "0029_webhook_security"
    assert revision.down_revision == "0028_usage_governance"
    assert "CREATE TABLE app.webhook_integrations" in sql
    assert "CREATE TABLE app.webhook_replay_nonces" in sql
    assert "uq_webhook_replay_nonces_integration_nonce" in sql
    assert "CREATE TABLE app.webhook_delivery_audits" in sql
    assert "BEFORE UPDATE OR DELETE ON app.webhook_delivery_audits" in sql
    assert "updated_at" not in WebhookDeliveryAudit.__table__.c
