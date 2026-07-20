from base64 import urlsafe_b64encode
import json
import logging
from uuid import UUID

import pytest
from pydantic import SecretStr

from crypto_alert_v2.notifications.credentials import (
    NotificationCredentialCipher,
    NotificationCredentialError,
    notification_credential_cipher_from_environment,
)


DESTINATION_ID = UUID("11111111-1111-4111-8111-111111111111")
TENANT_ID = UUID("22222222-2222-4222-8222-222222222222")
WORKSPACE_ID = UUID("33333333-3333-4333-8333-333333333333")
OWNER_USER_ID = UUID("44444444-4444-4444-8444-444444444444")
SCOPE = {
    "destination_id": DESTINATION_ID,
    "tenant_id": TENANT_ID,
    "workspace_id": WORKSPACE_ID,
    "owner_user_id": OWNER_USER_ID,
    "channel": "bark",
}


def _encoded(key: bytes) -> str:
    return urlsafe_b64encode(key).decode("ascii").rstrip("=")


def _encrypt(
    cipher: NotificationCredentialCipher,
    credential: str,
) -> bytes:
    return cipher.encrypt(SecretStr(credential), **SCOPE)


def test_keyring_writes_with_active_key_and_decrypts_previous_version() -> None:
    previous = NotificationCredentialCipher(key=b"1" * 32, key_version="v1")
    previous_ciphertext = _encrypt(previous, "previous-device-key")
    keyring = NotificationCredentialCipher(
        key=b"2" * 32,
        key_version="v2",
        decrypt_keys={"v1": b"1" * 32},
    )

    current_ciphertext = _encrypt(keyring, "current-device-key")

    assert keyring.key_version == "v2"
    assert keyring.supports_decryption("v1") is True
    assert keyring.supports_decryption("v2") is True
    assert keyring.supports_decryption("retired") is False
    assert (
        keyring.decrypt(
            previous_ciphertext,
            key_version="v1",
            **SCOPE,
        ).get_secret_value()
        == "previous-device-key"
    )
    assert (
        keyring.decrypt(
            current_ciphertext,
            key_version="v2",
            **SCOPE,
        ).get_secret_value()
        == "current-device-key"
    )
    with pytest.raises(NotificationCredentialError):
        previous.decrypt(current_ciphertext, key_version="v2", **SCOPE)


def test_unknown_or_retired_key_version_fails_closed() -> None:
    previous = NotificationCredentialCipher(key=b"1" * 32, key_version="v1")
    ciphertext = _encrypt(previous, "device-key-that-must-not-leak")
    keyring = NotificationCredentialCipher(key=b"2" * 32, key_version="v2")

    with pytest.raises(
        NotificationCredentialError,
        match="^notification credential is unavailable$",
    ) as error:
        keyring.decrypt(ciphertext, key_version="v1", **SCOPE)

    message = str(error.value)
    assert "device-key-that-must-not-leak" not in message
    assert ciphertext.hex() not in message


def test_environment_loads_json_decrypt_only_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_key = b"1" * 32
    current_key = b"2" * 32
    previous = NotificationCredentialCipher(key=previous_key, key_version="v1")
    previous_ciphertext = _encrypt(previous, "environment-device-key")
    monkeypatch.setenv("NOTIFICATION_CREDENTIAL_KEY", _encoded(current_key))
    monkeypatch.setenv("NOTIFICATION_CREDENTIAL_KEY_VERSION", "v2")
    monkeypatch.setenv(
        "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS",
        json.dumps({"v1": _encoded(previous_key)}),
    )

    keyring = notification_credential_cipher_from_environment()

    assert keyring is not None
    assert keyring.key_version == "v2"
    assert (
        keyring.decrypt(
            previous_ciphertext,
            key_version="v1",
            **SCOPE,
        ).get_secret_value()
        == "environment-device-key"
    )
    current_ciphertext = _encrypt(keyring, "new-environment-device-key")
    assert (
        keyring.decrypt(
            current_ciphertext,
            key_version="v2",
            **SCOPE,
        ).get_secret_value()
        == "new-environment-device-key"
    )


@pytest.mark.parametrize(
    "encoded_keys, expected_error",
    (
        ("[]", "must be a JSON object"),
        ('{"v1": 1}', "must map versions to Base64 keys"),
        ('{"v1":"first","v1":"second"}', "contains duplicate versions"),
        ('{"unsafe version":"AAAA"}', "key version is invalid"),
    ),
)
def test_environment_rejects_unsafe_decrypt_key_json_without_echoing_values(
    monkeypatch: pytest.MonkeyPatch,
    encoded_keys: str,
    expected_error: str,
) -> None:
    active_key = _encoded(b"2" * 32)
    monkeypatch.setenv("NOTIFICATION_CREDENTIAL_KEY", active_key)
    monkeypatch.setenv("NOTIFICATION_CREDENTIAL_KEY_VERSION", "v2")
    monkeypatch.setenv("NOTIFICATION_CREDENTIAL_DECRYPT_KEYS", encoded_keys)

    with pytest.raises(ValueError, match=expected_error) as error:
        notification_credential_cipher_from_environment()

    assert active_key not in str(error.value)
    assert encoded_keys not in str(error.value)


def test_environment_rejects_active_version_in_decrypt_only_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key = _encoded(b"2" * 32)
    monkeypatch.setenv("NOTIFICATION_CREDENTIAL_KEY", active_key)
    monkeypatch.setenv("NOTIFICATION_CREDENTIAL_KEY_VERSION", "v2")
    monkeypatch.setenv(
        "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS",
        json.dumps({"v2": active_key}),
    )

    with pytest.raises(ValueError, match="conflicts with the active key version"):
        notification_credential_cipher_from_environment()


def test_keyring_operations_do_not_log_sensitive_material(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plaintext = "logging-canary-device-key"
    key = b"sensitive-key-material-canary!!".ljust(32, b"!")
    keyring = NotificationCredentialCipher(key=key, key_version="v2")

    with caplog.at_level(logging.DEBUG):
        ciphertext = _encrypt(keyring, plaintext)
        keyring.decrypt(ciphertext, key_version="v2", **SCOPE)
        with pytest.raises(NotificationCredentialError):
            keyring.decrypt(ciphertext, key_version="retired", **SCOPE)

    output = "\n".join(record.getMessage() for record in caplog.records)
    assert plaintext not in output
    assert key.decode("ascii") not in output
    assert ciphertext.hex() not in output
