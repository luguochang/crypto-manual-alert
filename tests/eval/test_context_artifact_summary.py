from __future__ import annotations

import json

from crypto_manual_alert.eval.context_artifact_summary import context_artifacts_summary


def test_context_artifacts_summary_preserves_safe_refs_without_raw_payloads():
    summary = context_artifacts_summary(
        {
            "run_context": {
                "artifacts": {
                    "evidence_count": 2,
                    "contribution_count": 1,
                    "has_lead_plan": True,
                    "has_decision_input": True,
                    "lead_plan_ref": {
                        "plan_id": "lead-1",
                        "artifact_hash": "sha256:lead",
                        "raw_plan": "must not leak",
                    },
                    "decision_input_ref": {
                        "input_ref": "trace:1:decision_input",
                        "input_hash": "sha256:decision",
                        "raw_payload": "must not leak",
                    },
                    "gate_result_refs": {
                        "gate_candidate": {
                            "artifact_ref": "candidate:gate_candidate",
                            "artifact_hash": "sha256:gate",
                            "passed": True,
                            "raw_reason": "must not leak",
                        }
                    },
                    "evidence_refs": [
                        {
                            "evidence_id": "ev-1",
                            "data_type": "mark",
                            "source_type": "exchange_native",
                            "source_url": "https://exchange.example/mark",
                            "snippet": "must not leak",
                        }
                    ],
                    "contribution_refs": [
                        {
                            "contribution_id": "c-1",
                            "agent_name": "DataQualityAgent",
                            "status": "completed",
                            "input_ref": "trace:1:input",
                            "output_hash": "sha256:output",
                            "raw_payload": "must not leak",
                        }
                    ],
                }
            }
        }
    )

    assert summary == {
        "evidence_count": 2,
        "contribution_count": 1,
        "has_lead_plan": True,
        "has_decision_input": True,
        "lead_plan_ref": {"plan_id": "lead-1", "artifact_hash": "sha256:lead"},
        "decision_input_ref": {
            "input_ref": "trace:1:decision_input",
            "input_hash": "sha256:decision",
        },
        "gate_result_refs": {
            "gate_candidate": {
                "artifact_ref": "candidate:gate_candidate",
                "artifact_hash": "sha256:gate",
                "passed": True,
            }
        },
        "evidence_refs": [
            {
                "evidence_id": "ev-1",
                "data_type": "mark",
                "source_type": "exchange_native",
                "source_url": "https://exchange.example/mark",
            }
        ],
        "contribution_refs": [
            {
                "contribution_id": "c-1",
                "agent_name": "DataQualityAgent",
                "status": "completed",
                "input_ref": "trace:1:input",
                "output_hash": "sha256:output",
            }
        ],
    }
    rendered = json.dumps(summary, ensure_ascii=False).lower()
    assert "raw" not in rendered
    assert "must not leak" not in rendered
