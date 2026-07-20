from __future__ import annotations

from langchain.agents.middleware import PIIMiddleware


SECRET_PATTERN = (
    r"(?i)(?:"
    r"\b(?:authorization|proxy-authorization)\s*:\s*(?:bearer\s+)?[^\s,;]+"
    r"|\b(?:cookie|set-cookie)\s*:\s*[^\r\n]+"
    r"|\b(?:sk-[a-z0-9_-]{8,}|lsv2_[a-z0-9_-]{8,}|pk-lf-[a-z0-9_-]{8,})\b"
    r"|\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"client[_ -]?secret|bark[_ -]?key|langsmith[_ -]?key|"
    r"langfuse[_ -]?key|password)\s*[=:]\s*[^\s,;}]+"
    r")"
)
PHONE_PATTERN = (
    r"(?x)(?:"
    r"\b1[3-9]\d{9}\b"
    r"|(?:\+\d{1,3}[ .-]?)?\(?\d{2,4}\)?[ .-]\d{3,4}[ .-]\d{4}\b"
    r")"
)


def _redacting_middleware(
    pii_type: str, *, detector: str | None = None
) -> PIIMiddleware:
    return PIIMiddleware(
        pii_type,
        detector=detector,
        strategy="redact",
        apply_to_input=True,
        apply_to_output=True,
        apply_to_tool_results=True,
    )


def secret_redaction_middleware() -> tuple[PIIMiddleware, ...]:
    return (
        _redacting_middleware("email"),
        _redacting_middleware("credit_card"),
        _redacting_middleware("ip"),
        _redacting_middleware("mac_address"),
        _redacting_middleware("phone", detector=PHONE_PATTERN),
        _redacting_middleware("secret", detector=SECRET_PATTERN),
    )


__all__ = ["PHONE_PATTERN", "SECRET_PATTERN", "secret_redaction_middleware"]
