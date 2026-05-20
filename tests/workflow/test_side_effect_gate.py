from crypto_manual_alert.workflow.side_effect_gate import evaluate_side_effect_gate


def test_side_effect_gate_fails_closed_without_context_policy():
    result = evaluate_side_effect_gate(None)

    assert result.allow_production_journal_write is False
    assert result.allow_notification_intent is False
    assert result.skip_reason == "side_effect_policy_missing"
    assert result.to_public_dict() == {
        "allow_production_journal_write": False,
        "allow_notification_intent": False,
        "skip_reason": "side_effect_policy_missing",
    }


def test_side_effect_gate_uses_context_policy_without_widening_permissions():
    result = evaluate_side_effect_gate(
        {
            "side_effect_policy": {
                "allow_production_journal_write": True,
                "allow_notification_intent": False,
            }
        }
    )

    assert result.allow_production_journal_write is True
    assert result.allow_notification_intent is False
    assert result.skip_reason == "side_effect_policy"
