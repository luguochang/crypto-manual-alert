from datetime import UTC, datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from crypto_alert_v2.auth.internal_token import (
    InternalTokenIssuer,
    InternalTokenVerifier,
)
from crypto_alert_v2.config import Settings


ISSUER = "https://product.example.com"
AUDIENCE = "crypto-alert-agent-server"
MAX_TTL_SECONDS = 60


def _key_pair() -> tuple[str, str]:
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


def _issuer(private_key: str, kid: str) -> InternalTokenIssuer:
    return InternalTokenIssuer(
        private_key=private_key,
        key_id=kid,
        issuer=ISSUER,
        audience=AUDIENCE,
        ttl_seconds=MAX_TTL_SECONDS,
    )


def _service_token(issuer: InternalTokenIssuer) -> str:
    return issuer.issue(
        subject="worker-1",
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        roles=("worker",),
        permissions=("analysis:write",),
    )


def test_internal_jwt_overlap_accepts_old_and_new_then_retires_old(tmp_path) -> None:
    old_private, old_public = _key_pair()
    new_private, new_public = _key_pair()
    new_public_key_file = tmp_path / "jwt-v2-public.pem"
    new_public_key_file.write_text(new_public)
    settings = Settings(
        _env_file=None,
        app_environment="production",
        internal_jwt_public_keys={"jwt-v1": old_public},
        INTERNAL_JWT_KID="jwt-v2",
        internal_jwt_public_key_file=str(new_public_key_file),
        internal_jwt_issuer=ISSUER,
        agent_server_internal_jwt_audience=AUDIENCE,
    )
    old_token = _service_token(_issuer(old_private, "jwt-v1"))
    new_token = _service_token(_issuer(new_private, "jwt-v2"))

    overlap_verifier = InternalTokenVerifier(
        public_keys=settings.internal_jwt_public_keys,
        issuer=settings.internal_jwt_issuer,
        audience=settings.agent_server_internal_jwt_audience,
        max_ttl_seconds=settings.internal_jwt_max_ttl_seconds,
    )

    assert overlap_verifier.verify(old_token)["sub"] == "worker-1"
    assert overlap_verifier.verify(new_token)["sub"] == "worker-1"

    retired_verifier = InternalTokenVerifier(
        public_keys={"jwt-v2": new_public},
        issuer=ISSUER,
        audience=AUDIENCE,
        max_ttl_seconds=MAX_TTL_SECONDS,
    )

    with pytest.raises(PermissionError, match="unknown signing key"):
        retired_verifier.verify(old_token)
    assert retired_verifier.verify(new_token)["sub"] == "worker-1"


def test_internal_jwt_overlap_preserves_sixty_second_maximum() -> None:
    private_key, public_key = _key_pair()
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "worker-1",
        "token_use": "worker",
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "roles": ["worker"],
        "permissions": ["analysis:write"],
        "identity_issuer": "https://identity.example.com",
        "jti": "rotation-contract",
        "iat": now,
        "exp": now + MAX_TTL_SECONDS + 1,
    }
    token = jwt.encode(
        payload, private_key, algorithm="RS256", headers={"kid": "jwt-v2"}
    )
    verifier = InternalTokenVerifier(
        public_keys={"jwt-v2": public_key},
        issuer=ISSUER,
        audience=AUDIENCE,
        max_ttl_seconds=MAX_TTL_SECONDS,
    )

    with pytest.raises(PermissionError, match="lifetime"):
        verifier.verify(token)
