from __future__ import annotations

from base64 import b64decode
from binascii import Error as BinasciiError
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import hmac
import re
from secrets import token_urlsafe
from typing import Callable, Sequence

from crypto_alert_v2.integrations.secret_store import SecretStore


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_EVENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_NONCE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


class WebhookSignatureError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class WebhookSignature:
    key_id: str
    timestamp: int
    nonce: str
    event_id: str
    signature: str

    def headers(self) -> dict[str, str]:
        return {
            "X-Webhook-Key-Id": self.key_id,
            "X-Webhook-Timestamp": str(self.timestamp),
            "X-Webhook-Nonce": self.nonce,
            "X-Webhook-Event-Id": self.event_id,
            "X-Webhook-Signature": f"v1={self.signature}",
        }


class WebhookSigner:
    def __init__(
        self,
        *,
        secret_store: SecretStore,
        active_key_id: str,
        accepted_key_ids: Sequence[str] = (),
        max_age_seconds: int = 300,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.active_key_id = _validate_key_id(active_key_id)
        self.accepted_key_ids = tuple(
            dict.fromkeys(
                [self.active_key_id]
                + [_validate_key_id(item) for item in accepted_key_ids]
            )
        )
        if max_age_seconds < 1 or max_age_seconds > 3600:
            raise ValueError("webhook max age must be between 1 and 3600 seconds")
        self._secret_store = secret_store
        self._max_age_seconds = max_age_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def sign(
        self,
        payload: bytes,
        *,
        event_id: str,
        timestamp: int | None = None,
        nonce: str | None = None,
    ) -> WebhookSignature:
        normalized_event_id = _validate_event_id(event_id)
        issued_at = timestamp if timestamp is not None else int(self._now().timestamp())
        normalized_nonce = nonce or token_urlsafe(24)
        _validate_nonce(normalized_nonce)
        digest = hmac.new(
            self._key(self.active_key_id),
            _canonical_message(
                payload,
                timestamp=issued_at,
                nonce=normalized_nonce,
                event_id=normalized_event_id,
            ),
            "sha256",
        ).hexdigest()
        return WebhookSignature(
            key_id=self.active_key_id,
            timestamp=issued_at,
            nonce=normalized_nonce,
            event_id=normalized_event_id,
            signature=digest,
        )

    def verify(self, payload: bytes, signature: WebhookSignature) -> str:
        key_id = _validate_key_id(signature.key_id)
        event_id = _validate_event_id(signature.event_id)
        _validate_nonce(signature.nonce)
        if key_id not in self.accepted_key_ids:
            raise WebhookSignatureError("unknown_key", "webhook signing key is unknown")
        age = abs(int(self._now().timestamp()) - signature.timestamp)
        if age > self._max_age_seconds:
            raise WebhookSignatureError("stale_timestamp", "webhook timestamp is stale")
        expected = hmac.new(
            self._key(key_id),
            _canonical_message(
                payload,
                timestamp=signature.timestamp,
                nonce=signature.nonce,
                event_id=event_id,
            ),
            "sha256",
        ).hexdigest()
        if not hmac.compare_digest(expected, signature.signature):
            raise WebhookSignatureError("signature_invalid", "webhook signature is invalid")
        return sha256(payload).hexdigest()

    def _key(self, key_id: str) -> bytes:
        secret = self._secret_store.get_secret(
            f"webhook_signing_{_secret_key_component(key_id)}"
        )
        if secret is None:
            raise WebhookSignatureError(
                "key_unavailable", "webhook signing key is unavailable"
            )
        try:
            encoded = secret.get_secret_value().strip().encode("ascii")
            key = b64decode(
                encoded + (b"=" * (-len(encoded) % 4)),
                altchars=b"-_",
                validate=True,
            )
        except (BinasciiError, UnicodeEncodeError):
            raise WebhookSignatureError(
                "key_unavailable", "webhook signing key is unavailable"
            ) from None
        if len(key) != 32:
            raise WebhookSignatureError(
                "key_unavailable", "webhook signing key is unavailable"
            )
        return key

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("webhook clock must be timezone-aware")
        return now.astimezone(UTC)


def _canonical_message(
    payload: bytes,
    *,
    timestamp: int,
    nonce: str,
    event_id: str,
) -> bytes:
    return "\n".join(
        ("v1", str(timestamp), nonce, event_id, sha256(payload).hexdigest())
    ).encode("ascii")


def _validate_key_id(value: str) -> str:
    normalized = value.strip()
    if not _KEY_ID.fullmatch(normalized):
        raise ValueError("webhook key ID is invalid")
    return normalized


def _validate_event_id(value: str) -> str:
    normalized = value.strip()
    if not _EVENT_ID.fullmatch(normalized):
        raise ValueError("webhook event ID is invalid")
    return normalized


def _validate_nonce(value: str) -> str:
    normalized = value.strip()
    if not _NONCE.fullmatch(normalized):
        raise ValueError("webhook nonce is invalid")
    return normalized


def _secret_key_component(key_id: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", key_id.lower())


__all__ = [
    "WebhookSignature",
    "WebhookSignatureError",
    "WebhookSigner",
]
