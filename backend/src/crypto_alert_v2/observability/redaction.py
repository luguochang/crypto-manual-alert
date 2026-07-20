from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
import ipaddress
import re
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from langfuse.types import (
    MaskOtelSpansParams,
    MaskOtelSpansResult,
    OtelSpanPatch,
)

REDACTED = "[REDACTED]"


def _model_dump_json_compatible(value: Any) -> Any:
    """Serialize Pydantic-like values across LangGraph's model_dump variants."""
    model_dump = getattr(value, "model_dump", None)
    if not callable(model_dump):
        return value
    try:
        return model_dump(mode="json")
    except TypeError as exc:
        if "unexpected keyword argument 'mode'" not in str(exc):
            raise
        return model_dump()


def _dataclass_mapping(value: Any) -> dict[str, Any]:
    return {field.name: getattr(value, field.name) for field in fields(value)}


_SAFE_TOKEN_KEYS = frozenset(
    {
        "acceptedpredictiontokens",
        "audiotokens",
        "cachedtokens",
        "cachecreationinputtokens",
        "cachereadinputtokens",
        "completiontokens",
        "completiontokendetails",
        "inputtokens",
        "inputtokendetails",
        "maxtokens",
        "outputtokens",
        "outputtokendetails",
        "prompttokens",
        "prompttokendetails",
        "reasoningtokens",
        "rejectedpredictiontokens",
        "tokencount",
        "tokenusage",
        "totaltokens",
    }
)
_SENSITIVE_KEY_MARKERS = (
    "accesstoken",
    "apikey",
    "authorization",
    "barkkey",
    "clientsecret",
    "cookie",
    "credential",
    "cursorkey",
    "devicekey",
    "encryptionkey",
    "langfusekey",
    "langsmithkey",
    "passphrase",
    "password",
    "privatekey",
    "refreshtoken",
    "secret",
    "sessiontoken",
    "signingkey",
    "token",
)
_SENSITIVE_EXACT_KEYS = frozenset(
    {
        "token",
        "setcookie",
        "proxyauthorization",
        "xapikey",
    }
)

_URL_PATTERN = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s<>'\"\[\]{}]+")
_BEARER_PATTERN = re.compile(
    r"(?i)\b(bearer)\s+[a-z0-9._~+/=-]+",
)
_HEADER_PATTERN = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key)"
    r"(\s*:\s*)[^\r\n,}]+",
)
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"client[_ -]?secret|device[_ -]?key|local[_ -]?token|passphrase|"
    r"password|private[_ -]?key|secret|token)\b\s*[=:]\s*[\"']?)"
    r"[^\s\"',;}]+",
)
_KNOWN_TOKEN_PATTERN = re.compile(
    r"(?i)\b(?:sk|pk)-(?:lf-)?[a-z0-9_-]{8,}\b|\blsv2_[a-z0-9_-]{8,}\b",
)
_EMAIL_PATTERN = re.compile(
    r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}(?![a-z0-9._%+-])"
)
_CREDIT_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_IPV4_PATTERN = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_MAC_PATTERN = re.compile(
    r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"
)
_PHONE_PATTERN = re.compile(
    r"(?x)(?:"
    r"\b1[3-9]\d{9}\b"
    r"|(?:\+\d{1,3}[ .-]?)?\(?\d{2,4}\)?[ .-]\d{3,4}[ .-]\d{4}\b"
    r")"
)


@dataclass(frozen=True)
class RedactionEvent:
    event: str
    boundary: str
    redaction_count: int
    categories: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "boundary": self.boundary,
            "redaction_count": self.redaction_count,
            "categories": list(self.categories),
        }


@dataclass(frozen=True)
class RedactionResult:
    value: Any
    event: RedactionEvent


class _RedactionTracker:
    def __init__(self) -> None:
        self.count = 0
        self.categories: set[str] = set()

    def record(self, category: str, count: int = 1) -> None:
        self.count += count
        self.categories.add(category)


def _normalized_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def is_sensitive_key(value: str) -> bool:
    normalized = _normalized_key(value)
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    non_token_markers = (
        marker for marker in _SENSITIVE_KEY_MARKERS if marker != "token"
    )
    if any(marker in normalized for marker in non_token_markers):
        return True
    leaf = re.split(r"[.:/]", value)[-1]
    if normalized in _SAFE_TOKEN_KEYS or _normalized_key(leaf) in _SAFE_TOKEN_KEYS:
        return False
    return "token" in normalized


def _clean_netloc(parts: SplitResult) -> str:
    hostname = parts.hostname
    if not hostname:
        return ""
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    try:
        port = parts.port
    except ValueError:
        port = None
    return f"{rendered_host}:{port}" if port is not None else rendered_host


def redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return REDACTED
    if not parts.scheme or not parts.netloc:
        return value
    path = parts.path
    if (parts.hostname or "").casefold() == "api.day.app" and path not in {
        "",
        "/",
        "/push",
    }:
        path = f"/{REDACTED}"
    return urlunsplit((parts.scheme, _clean_netloc(parts), path, "", ""))


def _redact_urls(value: str, tracker: _RedactionTracker) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        suffix = ""
        while raw_url and raw_url[-1] in ".),;":
            suffix = raw_url[-1] + suffix
            raw_url = raw_url[:-1]
        redacted_url = redact_url(raw_url)
        if redacted_url != raw_url:
            tracker.record("url")
        return redacted_url + suffix

    return _URL_PATTERN.sub(replace, value)


def _substitute(
    pattern: re.Pattern[str],
    value: str,
    replacement: str | Any,
    category: str,
    tracker: _RedactionTracker,
) -> str:
    redacted, count = pattern.subn(replacement, value)
    if count:
        tracker.record(category, count)
    return redacted


def _redact_text(value: str, tracker: _RedactionTracker) -> str:
    redacted = _redact_urls(value, tracker)
    redacted = _redact_pii(redacted, tracker)
    redacted = _substitute(
        _HEADER_PATTERN,
        redacted,
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
        "header",
        tracker,
    )
    redacted = _substitute(
        _ASSIGNMENT_PATTERN,
        redacted,
        lambda match: f"{match.group(1)}{REDACTED}",
        "api_key",
        tracker,
    )
    redacted = _substitute(
        _BEARER_PATTERN,
        redacted,
        lambda match: f"{match.group(1)} {REDACTED}",
        "bearer",
        tracker,
    )
    return _substitute(
        _KNOWN_TOKEN_PATTERN,
        redacted,
        REDACTED,
        "known_token",
        tracker,
    )


def _redact_pii(value: str, tracker: _RedactionTracker) -> str:
    redacted = _substitute(
        _EMAIL_PATTERN,
        value,
        REDACTED,
        "pii_email",
        tracker,
    )
    redacted = _replace_validated(
        _CREDIT_CARD_PATTERN,
        redacted,
        validator=_is_credit_card,
        category="pii_credit_card",
        tracker=tracker,
    )
    redacted = _replace_validated(
        _IPV4_PATTERN,
        redacted,
        validator=_is_ip_address,
        category="pii_ip",
        tracker=tracker,
    )
    redacted = _substitute(
        _MAC_PATTERN,
        redacted,
        REDACTED,
        "pii_mac_address",
        tracker,
    )
    return _substitute(
        _PHONE_PATTERN,
        redacted,
        REDACTED,
        "pii_phone",
        tracker,
    )


def _replace_validated(
    pattern: re.Pattern[str],
    value: str,
    *,
    validator: Any,
    category: str,
    tracker: _RedactionTracker,
) -> str:
    def replace(match: re.Match[str]) -> str:
        candidate = match.group(0)
        if not validator(candidate):
            return candidate
        tracker.record(category)
        return REDACTED

    return pattern.sub(replace, value)


def _is_credit_card(value: str) -> bool:
    digits = [int(character) for character in value if character.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def redact_text(value: str) -> str:
    return _redact_text(value, _RedactionTracker())


def _is_secret_value(value: Any) -> bool:
    return callable(getattr(value, "get_secret_value", None))


def _redact_value(value: Any, tracker: _RedactionTracker) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            text_key = str(key)
            if is_sensitive_key(text_key):
                tracker.record("sensitive_key")
                redacted[text_key] = REDACTED
            else:
                redacted[text_key] = _redact_value(nested, tracker)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item, tracker) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item, tracker) for item in value)
    if isinstance(value, set):
        return [_redact_value(item, tracker) for item in sorted(value, key=repr)]
    if isinstance(value, bytes):
        return _redact_text(value.decode("utf-8", errors="replace"), tracker)
    if _is_secret_value(value):
        tracker.record("secret_value")
        return REDACTED
    if isinstance(value, str):
        return _redact_text(value, tracker)
    if isinstance(value, BaseException):
        tracker.record("exception")
        return {"error_type": type(value).__name__}
    if is_dataclass(value) and not isinstance(value, type):
        return _redact_value(_dataclass_mapping(value), tracker)
    if callable(getattr(value, "model_dump", None)):
        return _redact_value(_model_dump_json_compatible(value), tracker)
    return value


def redact_with_event(value: Any, *, boundary: str) -> RedactionResult:
    tracker = _RedactionTracker()
    redacted = _redact_value(value, tracker)
    return RedactionResult(
        value=redacted,
        event=RedactionEvent(
            event="observability_egress_redaction",
            boundary=boundary,
            redaction_count=tracker.count,
            categories=tuple(sorted(tracker.categories)),
        ),
    )


def redact_payload(value: Any) -> Any:
    return redact_with_event(value, boundary="observability").value


def mask_langfuse_payload(*, data: Any) -> Any:
    """Adapt the project redactor to Langfuse's keyword-only mask contract."""
    return redact_payload(data)


def redact_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            text_key = str(key)
            if is_sensitive_key(text_key):
                continue
            redacted[text_key] = redact_metadata(nested)
        return redacted
    if isinstance(value, list):
        return [redact_metadata(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_metadata(item) for item in value)
    if isinstance(value, set):
        return [redact_metadata(item) for item in sorted(value, key=repr)]
    if isinstance(value, bytes):
        return redact_text(value.decode("utf-8", errors="replace"))
    if _is_secret_value(value):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, BaseException):
        return {"error_type": type(value).__name__}
    if is_dataclass(value) and not isinstance(value, type):
        return redact_metadata(_dataclass_mapping(value))
    if callable(getattr(value, "model_dump", None)):
        return redact_metadata(_model_dump_json_compatible(value))
    return value


def mask_langfuse_otel_spans(
    *,
    params: MaskOtelSpansParams,
) -> MaskOtelSpansResult | None:
    patches = {}
    for identifier, span in params.spans.items():
        replacements: dict[str, Any] = {}
        for key, value in span.attributes.items():
            redacted = REDACTED if is_sensitive_key(key) else redact_payload(value)
            if redacted != value:
                replacements[key] = redacted
        if replacements:
            patches[identifier] = OtelSpanPatch(set_attributes=replacements)
    return MaskOtelSpansResult(span_patches=patches) if patches else None
