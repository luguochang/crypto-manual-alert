import pytest
from pydantic import ValidationError

from crypto_alert_v2.graph.graph import graph
from crypto_alert_v2.graph.request import AnalysisRequest, ArtifactEdit, ReviewResponse


def test_canonical_graph_exposes_review_and_edit_revalidation_nodes() -> None:
    nodes = set(graph.get_graph().nodes)

    assert {
        "review_policy",
        "interrupt_review",
        "apply_edits",
        "commit_artifact",
    } <= nodes


def test_untrusted_analysis_request_cannot_select_review_policy() -> None:
    with pytest.raises(ValidationError, match="review_policy"):
        AnalysisRequest.model_validate(
            {
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
                "review_policy": "bypass",
            }
        )


@pytest.mark.parametrize("field", ("instrument", "horizon", "status"))
def test_artifact_edit_cannot_change_identity_or_commit_state(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        ArtifactEdit.model_validate({field: "BTC-USDT-SWAP"})


def test_artifact_edit_requires_at_least_one_allowed_change() -> None:
    with pytest.raises(ValidationError, match="at least one artifact edit"):
        ArtifactEdit.model_validate({})


def test_review_response_requires_edits_only_for_edit_action() -> None:
    with pytest.raises(ValidationError, match="require edits"):
        ReviewResponse.model_validate({"action": "edit"})

    with pytest.raises(ValidationError, match="only edit"):
        ReviewResponse.model_validate(
            {"action": "approve", "edits": {"entry_trigger": "65200"}}
        )
