from __future__ import annotations

from crypto_manual_alert.notification import BarkNotificationSink, NotificationSink
from crypto_manual_alert.notification.sinks import BarkNotificationSink as CanonicalBarkNotificationSink
from crypto_manual_alert.notification.sinks import NotificationSink as CanonicalNotificationSink


def test_notification_package_exports_canonical_sinks():
    assert NotificationSink is CanonicalNotificationSink
    assert BarkNotificationSink is CanonicalBarkNotificationSink
