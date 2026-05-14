__all__ = [
    "LlmTelemetry",
    "ObservabilityRecorder",
    "SpanHandle",
    "extract_chat_completion_telemetry",
    "extract_responses_telemetry",
    "record_llm_interaction",
    "use_observability",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name in {"ObservabilityRecorder", "SpanHandle", "record_llm_interaction", "use_observability"}:
        from . import observability

        return getattr(observability, name)
    from . import llm

    return getattr(llm, name)
