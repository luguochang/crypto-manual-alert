from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import jwt


REQUIRED_CLAIMS = (
    "iss",
    "aud",
    "sub",
    "tenant_id",
    "workspace_id",
    "roles",
    "permissions",
    "jti",
    "iat",
    "exp",
)
MAX_INTERNAL_TOKEN_TTL_SECONDS = 60


class InternalTokenIssuer:
    def __init__(
        self,
        *,
        private_key: str,
        key_id: str,
        issuer: str,
        audience: str,
        ttl_seconds: int = 60,
    ) -> None:
        if not all(value.strip() for value in (private_key, key_id, issuer, audience)):
            raise ValueError("internal JWT signing configuration is incomplete")
        if ttl_seconds < 1 or ttl_seconds > MAX_INTERNAL_TOKEN_TTL_SECONDS:
            raise ValueError("internal JWT lifetime must be between 1 and 60 seconds")
        self._private_key = private_key
        self._key_id = key_id
        self._issuer = issuer
        self._audience = audience
        self._ttl_seconds = ttl_seconds

    def issue(
        self,
        *,
        subject: str,
        tenant_id: str,
        workspace_id: str,
        roles: tuple[str, ...],
        permissions: tuple[str, ...],
    ) -> str:
        if not all(value.strip() for value in (subject, tenant_id, workspace_id)):
            raise ValueError("internal JWT identity is incomplete")
        now = int(datetime.now(UTC).timestamp())
        return jwt.encode(
            {
                "iss": self._issuer,
                "aud": self._audience,
                "sub": subject,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "roles": list(roles),
                "permissions": list(permissions),
                "jti": uuid4().hex,
                "iat": now,
                "exp": now + self._ttl_seconds,
            },
            self._private_key,
            algorithm="RS256",
            headers={"kid": self._key_id},
        )


class InternalTokenVerifier:
    def __init__(
        self,
        *,
        public_keys: Mapping[str, str],
        issuer: str,
        audience: str,
        max_ttl_seconds: int = MAX_INTERNAL_TOKEN_TTL_SECONDS,
        leeway_seconds: int = 5,
    ) -> None:
        if not public_keys:
            raise ValueError("at least one internal JWT public key is required")
        if not issuer or not audience:
            raise ValueError("internal JWT issuer and audience are required")
        if (
            max_ttl_seconds < 1
            or max_ttl_seconds > MAX_INTERNAL_TOKEN_TTL_SECONDS
        ):
            raise ValueError("max_ttl_seconds must be between 1 and 60 seconds")
        self._public_keys = dict(public_keys)
        self._issuer = issuer
        self._audience = audience
        self._max_ttl_seconds = max_ttl_seconds
        self._leeway_seconds = leeway_seconds

    def verify_authorization(self, authorization: str | None) -> dict[str, Any]:
        if authorization is None or not authorization.startswith("Bearer "):
            raise PermissionError("authenticated internal token is required")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise PermissionError("authenticated internal token is required")
        return self.verify(token)

    def verify(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise PermissionError("invalid internal token") from exc
        if header.get("alg") != "RS256":
            raise PermissionError("invalid internal token algorithm")
        kid = header.get("kid")
        key = self._public_keys.get(str(kid)) if kid else None
        if key is None:
            raise PermissionError("unknown signing key")
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway_seconds,
                options={"require": list(REQUIRED_CLAIMS)},
            )
        except jwt.PyJWTError as exc:
            raise PermissionError("invalid internal token") from exc

        issued_at = int(claims["iat"])
        expires_at = int(claims["exp"])
        if expires_at - issued_at > self._max_ttl_seconds:
            raise PermissionError("internal token lifetime exceeds the allowed maximum")
        for name in ("sub", "tenant_id", "workspace_id", "jti"):
            if not isinstance(claims.get(name), str) or not claims[name].strip():
                raise PermissionError("invalid internal token")
        for name in ("roles", "permissions"):
            value = claims.get(name)
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item for item in value
            ):
                raise PermissionError("invalid internal token")
        return claims


__all__ = [
    "InternalTokenIssuer",
    "InternalTokenVerifier",
    "MAX_INTERNAL_TOKEN_TTL_SECONDS",
    "REQUIRED_CLAIMS",
]
