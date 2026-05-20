__all__ = [
    "BarkNotificationSink",
    "NoopNotificationSink",
    "NotificationSink",
    "redact",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import sinks

    return getattr(sinks, name)
