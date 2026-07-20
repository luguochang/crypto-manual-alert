from __future__ import annotations

from base64 import b64decode
from binascii import Error as BinasciiError
import json
import os
from secrets import token_bytes
from typing import Mapping
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr


class NotificationCredentialError(RuntimeError):
    pass


class NotificationCredentialCipher:
    def __init__(
        self,
        *,
        key: bytes,
        key_version: str,
        decrypt_keys: Mapping[str, bytes] | None = None,
    ) -> None:
        self.key_version = _validate_key_version(key_version)
        active_cipher = _cipher_from_key(key)
        ciphers = {self.key_version: active_cipher}
        for decrypt_version, decrypt_key in (decrypt_keys or {}).items():
            normalized_version = _validate_key_version(decrypt_version)
            if normalized_version in ciphers:
                raise ValueError(
                    "notification credential decrypt key version conflicts with "
                    "the active key version"
                )
            ciphers[normalized_version] = _cipher_from_key(decrypt_key)
        self._active_cipher = active_cipher
        self._decrypt_ciphers = ciphers

    def supports_decryption(self, key_version: str) -> bool:
        return key_version in self._decrypt_ciphers

    @classmethod
    def from_urlsafe_base64(
        cls,
        encoded_key: str,
        *,
        key_version: str,
        decrypt_keys: Mapping[str, str] | None = None,
    ) -> "NotificationCredentialCipher":
        key = _decode_key(encoded_key)
        decoded_decrypt_keys = {
            version: _decode_key(encoded_decrypt_key)
            for version, encoded_decrypt_key in (decrypt_keys or {}).items()
        }
        return cls(
            key=key,
            key_version=key_version,
            decrypt_keys=decoded_decrypt_keys,
        )

    def encrypt(
        self,
        credential: SecretStr,
        *,
        destination_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_user_id: UUID,
        channel: str,
    ) -> bytes:
        plaintext = credential.get_secret_value().strip().encode("utf-8")
        if not plaintext or len(plaintext) > 255:
            raise ValueError("notification credential is invalid")
        nonce = token_bytes(12)
        return nonce + self._active_cipher.encrypt(
            nonce,
            plaintext,
            _aad(
                destination_id=destination_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=owner_user_id,
                channel=channel,
                key_version=self.key_version,
            ),
        )

    def decrypt(
        self,
        ciphertext: bytes,
        *,
        destination_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_user_id: UUID,
        channel: str,
        key_version: str,
    ) -> SecretStr:
        cipher = self._decrypt_ciphers.get(key_version)
        if cipher is None or len(ciphertext) <= 28:
            raise NotificationCredentialError("notification credential is unavailable")
        nonce = ciphertext[:12]
        try:
            plaintext = cipher.decrypt(
                nonce,
                ciphertext[12:],
                _aad(
                    destination_id=destination_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_user_id=owner_user_id,
                    channel=channel,
                    key_version=key_version,
                ),
            )
            value = plaintext.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError):
            raise NotificationCredentialError(
                "notification credential is unavailable"
            ) from None
        if not value.strip():
            raise NotificationCredentialError("notification credential is unavailable")
        return SecretStr(value)


def _aad(
    *,
    destination_id: UUID,
    tenant_id: UUID,
    workspace_id: UUID,
    owner_user_id: UUID,
    channel: str,
    key_version: str,
) -> bytes:
    return "\0".join(
        (
            "crypto-alert-v2:notification-destination:v1",
            str(tenant_id),
            str(workspace_id),
            str(owner_user_id),
            str(destination_id),
            channel,
            key_version,
        )
    ).encode("utf-8")


def _validate_key_version(key_version: str) -> str:
    normalized_version = key_version.strip()
    if (
        not normalized_version
        or len(normalized_version) > 64
        or not all(
            character.isascii() and (character.isalnum() or character in "._:-")
            for character in normalized_version
        )
    ):
        raise ValueError("notification credential key version is invalid")
    return normalized_version


def _cipher_from_key(key: bytes) -> AESGCM:
    if len(key) != 32:
        raise ValueError("notification credential key must contain exactly 32 bytes")
    return AESGCM(key)


def _decode_key(encoded_key: str) -> bytes:
    try:
        encoded = encoded_key.strip().encode("ascii")
        key = b64decode(
            encoded + (b"=" * (-len(encoded) % 4)),
            altchars=b"-_",
            validate=True,
        )
    except (BinasciiError, UnicodeEncodeError):
        raise ValueError(
            "notification credential key must be URL-safe Base64"
        ) from None
    return key


def _parse_decrypt_keys(encoded_keys: str) -> dict[str, str]:
    if len(encoded_keys) > 16_384:
        raise ValueError("NOTIFICATION_CREDENTIAL_DECRYPT_KEYS exceeds the size limit")

    def reject_duplicate_versions(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        parsed: dict[str, object] = {}
        for version, encoded_key in pairs:
            if version in parsed:
                raise ValueError(
                    "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS contains duplicate versions"
                )
            parsed[version] = encoded_key
        return parsed

    try:
        parsed = json.loads(
            encoded_keys,
            object_pairs_hook=reject_duplicate_versions,
        )
    except json.JSONDecodeError:
        raise ValueError(
            "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS must be a JSON object"
        ) from None
    if not isinstance(parsed, dict):
        raise ValueError("NOTIFICATION_CREDENTIAL_DECRYPT_KEYS must be a JSON object")
    if len(parsed) > 32:
        raise ValueError(
            "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS contains too many versions"
        )
    if not all(
        isinstance(version, str) and isinstance(encoded_key, str)
        for version, encoded_key in parsed.items()
    ):
        raise ValueError(
            "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS must map versions to Base64 keys"
        )
    return parsed


def notification_credential_cipher_from_environment() -> (
    NotificationCredentialCipher | None
):
    encoded_key = os.getenv("NOTIFICATION_CREDENTIAL_KEY", "").strip()
    if not encoded_key:
        return None
    key_version = os.getenv("NOTIFICATION_CREDENTIAL_KEY_VERSION", "v1").strip()
    encoded_decrypt_keys = os.getenv(
        "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS",
        "",
    ).strip()
    return NotificationCredentialCipher.from_urlsafe_base64(
        encoded_key,
        key_version=key_version,
        decrypt_keys=(
            _parse_decrypt_keys(encoded_decrypt_keys) if encoded_decrypt_keys else None
        ),
    )


__all__ = [
    "NotificationCredentialCipher",
    "NotificationCredentialError",
    "notification_credential_cipher_from_environment",
]
