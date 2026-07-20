from uuid import UUID

import pytest
from pydantic import SecretStr

from crypto_alert_v2.notifications.credentials import (
    NotificationCredentialCipher,
    NotificationCredentialError,
)


DESTINATION_ID = UUID("11111111-1111-4111-8111-111111111111")
TENANT_ID = UUID("22222222-2222-4222-8222-222222222222")
WORKSPACE_ID = UUID("33333333-3333-4333-8333-333333333333")
OWNER_USER_ID = UUID("44444444-4444-4444-8444-444444444444")


def _cipher(
    *, key: bytes = b"k" * 32, version: str = "v1"
) -> NotificationCredentialCipher:
    return NotificationCredentialCipher(key=key, key_version=version)


def _encrypt(
    cipher: NotificationCredentialCipher,
    *,
    credential: str = "bark-device-key-canary",
) -> bytes:
    return cipher.encrypt(
        SecretStr(credential),
        destination_id=DESTINATION_ID,
        tenant_id=TENANT_ID,
        workspace_id=WORKSPACE_ID,
        owner_user_id=OWNER_USER_ID,
        channel="bark",
    )


def test_notification_credential_ciphertext_hides_plaintext_and_round_trips() -> None:
    cipher = _cipher()

    ciphertext = _encrypt(cipher)
    decrypted = cipher.decrypt(
        ciphertext,
        destination_id=DESTINATION_ID,
        tenant_id=TENANT_ID,
        workspace_id=WORKSPACE_ID,
        owner_user_id=OWNER_USER_ID,
        channel="bark",
        key_version="v1",
    )

    assert b"bark-device-key-canary" not in ciphertext
    assert decrypted.get_secret_value() == "bark-device-key-canary"
    assert "bark-device-key-canary" not in repr(decrypted)


@pytest.mark.parametrize(
    "overrides",
    (
        {"destination_id": UUID("51111111-1111-4111-8111-111111111111")},
        {"tenant_id": UUID("52222222-2222-4222-8222-222222222222")},
        {"workspace_id": UUID("53333333-3333-4333-8333-333333333333")},
        {"owner_user_id": UUID("54444444-4444-4444-8444-444444444444")},
        {"channel": "email"},
    ),
)
def test_notification_credential_rejects_wrong_scope_aad(
    overrides: dict[str, object],
) -> None:
    cipher = _cipher()
    ciphertext = _encrypt(cipher)
    arguments: dict[str, object] = {
        "destination_id": DESTINATION_ID,
        "tenant_id": TENANT_ID,
        "workspace_id": WORKSPACE_ID,
        "owner_user_id": OWNER_USER_ID,
        "channel": "bark",
        "key_version": "v1",
    }
    arguments.update(overrides)

    with pytest.raises(
        NotificationCredentialError,
        match="notification credential is unavailable",
    ):
        cipher.decrypt(ciphertext, **arguments)  # type: ignore[arg-type]


def test_notification_credential_rejects_wrong_key_and_key_version() -> None:
    ciphertext = _encrypt(_cipher())
    decrypt_arguments = {
        "destination_id": DESTINATION_ID,
        "tenant_id": TENANT_ID,
        "workspace_id": WORKSPACE_ID,
        "owner_user_id": OWNER_USER_ID,
        "channel": "bark",
    }

    with pytest.raises(NotificationCredentialError):
        _cipher(key=b"z" * 32).decrypt(
            ciphertext,
            key_version="v1",
            **decrypt_arguments,
        )

    with pytest.raises(NotificationCredentialError):
        _cipher(version="v2").decrypt(
            ciphertext,
            key_version="v1",
            **decrypt_arguments,
        )


def test_notification_credential_validates_key_material_and_plaintext() -> None:
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        NotificationCredentialCipher(key=b"short", key_version="v1")

    with pytest.raises(ValueError, match="key version is invalid"):
        NotificationCredentialCipher(key=b"k" * 32, key_version="unsafe version")

    with pytest.raises(ValueError, match="credential is invalid"):
        _cipher().encrypt(
            SecretStr("   "),
            destination_id=DESTINATION_ID,
            tenant_id=TENANT_ID,
            workspace_id=WORKSPACE_ID,
            owner_user_id=OWNER_USER_ID,
            channel="bark",
        )
