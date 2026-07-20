from langchain.agents.middleware import PIIMiddleware

from crypto_alert_v2.agents.security import secret_redaction_middleware


def test_official_pii_middleware_detects_secret_canaries_on_every_boundary() -> None:
    middleware = secret_redaction_middleware()

    assert {item.pii_type for item in middleware} == {
        "email",
        "credit_card",
        "ip",
        "mac_address",
        "phone",
        "secret",
    }
    secret = next(item for item in middleware if item.pii_type == "secret")
    assert isinstance(secret, PIIMiddleware)
    assert secret.pii_type == "secret"
    assert secret.strategy == "redact"
    assert secret.apply_to_input is True
    assert secret.apply_to_output is True
    assert secret.apply_to_tool_results is True

    canaries = (
        "Authorization: Bearer sk-provider-secret-12345",
        "Cookie: session=secret-session-value",
        "api_key=sk-api-secret-12345",
        "bark_key=private-bark-secret",
        "langsmith_key=lsv2_trace-secret-12345",
        "langfuse_key=pk-lf-observe-secret-12345",
    )
    for canary in canaries:
        matches = secret.detector(canary)
        assert matches, canary
        assert all(match["value"] in canary for match in matches)

    pii_canaries = {
        "email": "trader@example.com",
        "credit_card": "4111 1111 1111 1111",
        "ip": "203.0.113.42",
        "mac_address": "00:1A:2B:3C:4D:5E",
        "phone": "+86 138 0013 8000",
    }
    for pii_type, canary in pii_canaries.items():
        detector = next(
            item.detector for item in middleware if item.pii_type == pii_type
        )
        assert detector(canary), pii_type
