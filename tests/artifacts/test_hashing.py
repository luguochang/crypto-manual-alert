from __future__ import annotations


def test_artifact_stable_hash_matches_legacy_decision_hash():
    from crypto_manual_alert.artifacts.hashing import stable_hash
    from crypto_manual_alert.decision.frozen_input import stable_hash as legacy_stable_hash

    payload = {"b": 2, "a": ["中文", {"nested": object()}]}

    assert stable_hash(payload) == legacy_stable_hash(payload)
