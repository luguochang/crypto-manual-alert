from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import jwt


COMMON_REQUIRED_CLAIMS = (
    "iss",
    "aud",
    "sub",
    "token_use",
    "jti",
    "iat",
    "exp",
)
REQUIRED_CLAIMS = COMMON_REQUIRED_CLAIMS
MAX_INTERNAL_TOKEN_TTL_SECONDS = 60
TOKEN_USES = frozenset({"identity_discovery", "user", "worker", "healthcheck"})
IDENTITY_DISCOVERY_AUDIENCE = "crypto-alert-identity-discovery"
_AUTHORITY_CLAIMS = frozenset({"tenant_id", "workspace_id", "roles", "permissions"})


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

    def issue_identity(self, *, issuer: str, subject: str) -> str:
        if self._audience != IDENTITY_DISCOVERY_AUDIENCE:
            raise ValueError("identity discovery token requires the discovery audience")
        return self._encode(
            subject=subject,
            token_use="identity_discovery",
            claims={"identity_issuer": _required(issuer, "identity issuer")},
        )

    def issue_scoped(
        self,
        *,
        issuer: str,
        subject: str,
        context_id: UUID | str,
    ) -> str:
        return self._encode(
            subject=subject,
            token_use="user",
            claims={
                "identity_issuer": _required(issuer, "identity issuer"),
                "context_id": str(UUID(str(context_id))),
            },
        )

    def issue(
        self,
        *,
        subject: str,
        tenant_id: str,
        workspace_id: str,
        roles: tuple[str, ...],
        permissions: tuple[str, ...],
        token_use: str = "worker",
        identity_issuer: str = "legacy",
        context_id: UUID | str | None = None,
    ) -> str:
        if token_use not in {"worker", "healthcheck"}:
            raise ValueError("service token use must be worker or healthcheck")
        if not all(value.strip() for value in (tenant_id, workspace_id)):
            raise ValueError("internal JWT service scope is incomplete")
        if not _valid_strings(roles) or not _valid_strings(
            permissions, allow_empty=True
        ):
            raise ValueError("internal JWT service permissions are incomplete")
        return self._encode(
            subject=subject,
            token_use=token_use,
            claims={
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "roles": list(roles),
                "permissions": list(permissions),
                "identity_issuer": _required(identity_issuer, "identity issuer"),
                **(
                    {"context_id": str(UUID(str(context_id)))}
                    if context_id is not None
                    else {}
                ),
            },
        )

    def _encode(
        self,
        *,
        subject: str,
        token_use: str,
        claims: Mapping[str, Any],
    ) -> str:
        if token_use not in TOKEN_USES:
            raise ValueError("invalid internal JWT token use")
        subject = _required(subject, "subject")
        now = int(datetime.now(UTC).timestamp())
        return jwt.encode(
            {
                "iss": self._issuer,
                "aud": self._audience,
                "sub": subject,
                "token_use": token_use,
                **claims,
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
        if max_ttl_seconds < 1 or max_ttl_seconds > MAX_INTERNAL_TOKEN_TTL_SECONDS:
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
                options={"require": list(COMMON_REQUIRED_CLAIMS)},
            )
        except jwt.PyJWTError as exc:
            raise PermissionError("invalid internal token") from exc

        issued_at = int(claims["iat"])
        expires_at = int(claims["exp"])
        if expires_at - issued_at > self._max_ttl_seconds:
            raise PermissionError("internal token lifetime exceeds the allowed maximum")
        for name in ("sub", "jti"):
            if not isinstance(claims.get(name), str) or not claims[name].strip():
                raise PermissionError("invalid internal token")
        token_use = claims.get("token_use")
        if token_use not in TOKEN_USES:
            raise PermissionError("invalid internal token use")
        self._validate_token_contract(claims, str(token_use))
        return claims

    def _validate_token_contract(
        self, claims: Mapping[str, Any], token_use: str
    ) -> None:
        if token_use in {"identity_discovery", "user"}:
            if any(name in claims for name in _AUTHORITY_CLAIMS):
                raise PermissionError("user token contains forbidden authority claims")
            _claim_string(claims, "identity_issuer")
            if token_use == "identity_discovery":
                if self._audience != IDENTITY_DISCOVERY_AUDIENCE:
                    raise PermissionError("invalid identity discovery audience")
                if "context_id" in claims:
                    raise PermissionError(
                        "identity discovery token cannot select a context"
                    )
                return
            if self._audience == IDENTITY_DISCOVERY_AUDIENCE:
                raise PermissionError("scoped user token requires a resource audience")
            try:
                UUID(_claim_string(claims, "context_id"))
            except ValueError as exc:
                raise PermissionError("invalid auth context") from exc
            return

        for name in ("tenant_id", "workspace_id"):
            _claim_string(claims, name)
        for name in ("roles", "permissions"):
            value = claims.get(name)
            if not isinstance(value, list) or not _valid_strings(
                value, allow_empty=name == "permissions"
            ):
                raise PermissionError("invalid internal service token")
        _claim_string(claims, "identity_issuer")
        if "context_id" in claims:
            try:
                UUID(_claim_string(claims, "context_id"))
            except ValueError as exc:
                raise PermissionError("invalid service auth context") from exc


def _required(value: str, name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"internal JWT {name} is incomplete")
    return normalized


def _claim_string(claims: Mapping[str, Any], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value.strip():
        raise PermissionError("invalid internal token")
    return value


def _valid_strings(values: object, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(values, (list, tuple))
        and (allow_empty or bool(values))
        and all(isinstance(value, str) and bool(value.strip()) for value in values)
    )


__all__ = [
    "COMMON_REQUIRED_CLAIMS",
    "IDENTITY_DISCOVERY_AUDIENCE",
    "InternalTokenIssuer",
    "InternalTokenVerifier",
    "MAX_INTERNAL_TOKEN_TTL_SECONDS",
    "REQUIRED_CLAIMS",
    "TOKEN_USES",
]
