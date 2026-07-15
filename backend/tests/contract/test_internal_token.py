from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from pydantic import ValidationError
import pytest

from crypto_alert_v2.auth.internal_token import (
    IDENTITY_DISCOVERY_AUDIENCE,
    InternalTokenIssuer,
    InternalTokenVerifier,
)
from crypto_alert_v2.config import Settings


ISSUER = "https://product.example.com"
AUDIENCE = "crypto-alert-product-api"


@pytest.fixture(scope="module")
def key_pair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def claims(now: datetime) -> dict[str, object]:
    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "oidc|user-1",
        "token_use": "worker",
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "roles": ["member"],
        "permissions": ["analysis:read", "analysis:write"],
        "identity_issuer": "https://identity.example.com",
        "jti": "request-1",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=60)).timestamp()),
    }


def encode(private_key: str, payload: dict[str, object], *, kid: str = "key-1") -> str:
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


def test_verifies_short_lived_server_owned_claims(key_pair: tuple[str, str]) -> None:
    private_key, public_key = key_pair
    now = datetime.now(UTC)
    verifier = InternalTokenVerifier(
        public_keys={"key-1": public_key},
        issuer=ISSUER,
        audience=AUDIENCE,
        max_ttl_seconds=60,
    )

    verified = verifier.verify(encode(private_key, claims(now)))

    assert verified["sub"] == "oidc|user-1"
    assert verified["tenant_id"] == "tenant-1"
    assert verified["workspace_id"] == "workspace-1"
    assert verified["token_use"] == "worker"


def test_issuer_and_verifier_share_the_production_contract(
    key_pair: tuple[str, str],
) -> None:
    private_key, public_key = key_pair
    issuer = InternalTokenIssuer(
        private_key=private_key,
        key_id="key-1",
        issuer=ISSUER,
        audience=AUDIENCE,
        ttl_seconds=60,
    )
    verifier = InternalTokenVerifier(
        public_keys={"key-1": public_key},
        issuer=ISSUER,
        audience=AUDIENCE,
        max_ttl_seconds=60,
    )

    token = issuer.issue(
        subject="oidc|user-1",
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )

    verified = verifier.verify(token)
    assert verified["sub"] == "oidc|user-1"
    assert verified["roles"] == ["member"]
    assert verified["token_use"] == "worker"


def test_identity_and_scoped_tokens_never_carry_authority_claims(
    key_pair: tuple[str, str],
) -> None:
    private_key, public_key = key_pair
    identity_issuer = InternalTokenIssuer(
        private_key=private_key,
        key_id="key-1",
        issuer=ISSUER,
        audience=IDENTITY_DISCOVERY_AUDIENCE,
    )
    identity_verifier = InternalTokenVerifier(
        public_keys={"key-1": public_key},
        issuer=ISSUER,
        audience=IDENTITY_DISCOVERY_AUDIENCE,
    )
    scoped_issuer = InternalTokenIssuer(
        private_key=private_key,
        key_id="key-1",
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    scoped_verifier = InternalTokenVerifier(
        public_keys={"key-1": public_key},
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    identity_claims = identity_verifier.verify(
        identity_issuer.issue_identity(
            issuer="https://identity.example.com",
            subject="oidc|user-1",
        )
    )
    scoped_claims = scoped_verifier.verify(
        scoped_issuer.issue_scoped(
            issuer="https://identity.example.com",
            subject="oidc|user-1",
            context_id="11111111-1111-4111-8111-111111111111",
        )
    )

    for verified in (identity_claims, scoped_claims):
        assert not {"tenant_id", "workspace_id", "roles", "permissions"}.intersection(
            verified
        )
    assert identity_claims["token_use"] == "identity_discovery"
    assert "context_id" not in identity_claims
    assert scoped_claims["token_use"] == "user"
    assert scoped_claims["context_id"] == "11111111-1111-4111-8111-111111111111"


def test_issuer_rejects_61_second_lifetime(key_pair: tuple[str, str]) -> None:
    private_key, _ = key_pair

    with pytest.raises(ValueError, match="between 1 and 60 seconds"):
        InternalTokenIssuer(
            private_key=private_key,
            key_id="key-1",
            issuer=ISSUER,
            audience=AUDIENCE,
            ttl_seconds=61,
        )


def test_default_verifier_rejects_trusted_61_second_token(
    key_pair: tuple[str, str],
) -> None:
    private_key, public_key = key_pair
    now = datetime.now(UTC)
    payload = claims(now)
    payload["exp"] = int((now + timedelta(seconds=61)).timestamp())
    verifier = InternalTokenVerifier(
        public_keys={"key-1": public_key},
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    with pytest.raises(PermissionError, match="lifetime"):
        verifier.verify(encode(private_key, payload))


def test_verifier_rejects_max_ttl_configuration_above_60(
    key_pair: tuple[str, str],
) -> None:
    _, public_key = key_pair

    with pytest.raises(ValueError, match="between 1 and 60 seconds"):
        InternalTokenVerifier(
            public_keys={"key-1": public_key},
            issuer=ISSUER,
            audience=AUDIENCE,
            max_ttl_seconds=61,
        )


def test_settings_default_internal_jwt_max_ttl_is_60_seconds() -> None:
    settings = Settings(_env_file=None, app_environment="test")

    assert settings.internal_jwt_max_ttl_seconds == 60


def test_settings_rejects_direct_internal_jwt_max_ttl_above_60() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_environment="test",
            internal_jwt_max_ttl_seconds=61,
        )


def test_settings_rejects_environment_internal_jwt_max_ttl_above_60(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTERNAL_JWT_MAX_TTL_SECONDS", "61")

    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_environment="test")


def test_rejects_unknown_key_id(key_pair: tuple[str, str]) -> None:
    private_key, public_key = key_pair
    verifier = InternalTokenVerifier(
        public_keys={"key-1": public_key},
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    with pytest.raises(PermissionError, match="unknown signing key"):
        verifier.verify(
            encode(private_key, claims(datetime.now(UTC)), kid="retired-key")
        )


def test_rejects_token_with_excessive_lifetime(key_pair: tuple[str, str]) -> None:
    private_key, public_key = key_pair
    now = datetime.now(UTC)
    payload = claims(now)
    payload["exp"] = int((now + timedelta(minutes=10)).timestamp())
    verifier = InternalTokenVerifier(
        public_keys={"key-1": public_key},
        issuer=ISSUER,
        audience=AUDIENCE,
        max_ttl_seconds=60,
    )

    with pytest.raises(PermissionError, match="lifetime"):
        verifier.verify(encode(private_key, payload))


@pytest.mark.parametrize(
    "missing",
    [
        "sub",
        "token_use",
        "tenant_id",
        "workspace_id",
        "jti",
        "iat",
        "exp",
    ],
)
def test_rejects_missing_required_claim(
    key_pair: tuple[str, str], missing: str
) -> None:
    private_key, public_key = key_pair
    payload = claims(datetime.now(UTC))
    payload.pop(missing)
    verifier = InternalTokenVerifier(
        public_keys={"key-1": public_key},
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    with pytest.raises(PermissionError, match="invalid internal token"):
        verifier.verify(encode(private_key, payload))
