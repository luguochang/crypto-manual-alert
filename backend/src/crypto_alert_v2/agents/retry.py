from langchain.agents.structured_output import StructuredOutputError

from crypto_alert_v2.providers.errors import TRANSIENT_MODEL_ERRORS


MODEL_TRANSPORT_RETRY_ERRORS = TRANSIENT_MODEL_ERRORS

# One official Runnable retry budget covers transport failures and one
# structured-output repair. Keeping both in one tuple prevents nested retries.
AGENT_RETRYABLE_ERRORS = (*TRANSIENT_MODEL_ERRORS, StructuredOutputError)


__all__ = ["AGENT_RETRYABLE_ERRORS", "MODEL_TRANSPORT_RETRY_ERRORS"]
