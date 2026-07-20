import pytest
from pydantic import ValidationError

from crypto_alert_v2.api.schemas import PublicReviewResponse
from crypto_alert_v2.domain.deep_research import (
    DeepResearchReport,
    DeepResearchSearchCoverage,
    materialize_deep_research_artifact,
)
from crypto_alert_v2.graph.graph import create_graph
from crypto_alert_v2.graph.request import (
    AnalysisRequest,
    ArtifactEdit,
    DeepResearchReportEdit,
    DeepResearchReviewPayload,
    ReviewResponse,
    validate_review_response_for_payload,
)
from tests.fixtures.golden_cases import NOW
from crypto_alert_v2.providers.search import WebEvidence


graph = create_graph()


def _research_report(
    *, claim: str = "Institutional adoption remains active."
) -> DeepResearchReport:
    return DeepResearchReport.model_validate(
        {
            "executive_summary": "Verified evidence supports a measured conclusion.",
            "sections": [
                {
                    "title": "Adoption",
                    "summary": "The source catalog supports the current finding.",
                    "findings": [{"claim": claim, "source_indexes": [1]}],
                }
            ],
            "risk_notes": ["The conclusion may change as new filings arrive."],
            "evidence_gaps": [],
        }
    )


def _research_review_payload() -> DeepResearchReviewPayload:
    evidence = WebEvidence(
        query="BTC institutional adoption",
        final_url="https://example.com/verified-btc-source",
        fetched_at=NOW,
        content_hash="c" * 64,
        title="Verified BTC source",
        source="test_search",
        excerpt="A verified source excerpt.",
        evidence_relation="supports",
    )
    return DeepResearchReviewPayload(
        symbol="BTC-USDT-SWAP",
        horizon="7d",
        review_iteration=1,
        artifact=materialize_deep_research_artifact(
            report=_research_report(),
            evidence=(evidence,),
            harness_mode="deepagents",
            search_coverage=DeepResearchSearchCoverage(
                status="complete",
                attempted_queries=1,
                successful_queries=1,
            ),
            model_audits=(),
        ),
    )


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


def test_research_review_payload_requires_a_draft_and_preserves_task_scope() -> None:
    payload = _research_review_payload()

    assert payload.kind == "deep_research_review"
    assert payload.symbol == "BTC-USDT-SWAP"
    assert payload.horizon == "7d"
    assert payload.artifact.status == "draft"

    with pytest.raises(ValidationError, match="draft"):
        DeepResearchReviewPayload.model_validate(
            {
                **payload.model_dump(mode="json"),
                "artifact": {
                    **payload.artifact.model_dump(mode="json"),
                    "status": "committed",
                },
            }
        )


def test_review_response_edit_type_is_validated_against_interrupt_kind() -> None:
    payload = _research_review_payload()
    research_response = ReviewResponse(
        action="edit",
        edits=DeepResearchReportEdit(
            report=_research_report(claim="Adoption remains active but uneven.")
        ),
    )

    validated = validate_review_response_for_payload(payload, research_response)
    assert isinstance(validated.edits, DeepResearchReportEdit)

    with pytest.raises(ValueError, match="deep research report edit"):
        validate_review_response_for_payload(
            payload,
            ReviewResponse(action="edit", edits=ArtifactEdit(entry_trigger="65200")),
        )


def test_research_review_rejects_noop_or_unknown_citation_edits() -> None:
    payload = _research_review_payload()

    with pytest.raises(ValueError, match="change the report"):
        validate_review_response_for_payload(
            payload,
            ReviewResponse(
                action="edit",
                edits=DeepResearchReportEdit(report=payload.artifact.report),
            ),
        )

    invalid_report = _research_report().model_dump(mode="json")
    invalid_report["sections"][0]["findings"][0]["source_indexes"] = [2]
    with pytest.raises(ValueError, match="unknown evidence source index"):
        validate_review_response_for_payload(
            payload,
            ReviewResponse(
                action="edit",
                edits=DeepResearchReportEdit.model_validate({"report": invalid_report}),
            ),
        )


def test_public_review_response_omits_absent_optional_fields() -> None:
    response = PublicReviewResponse.model_validate(
        {"action": "approve", "comment": "Approved after review."}
    )

    assert response.model_dump(mode="json") == {
        "action": "approve",
        "comment": "Approved after review.",
    }

    edited = PublicReviewResponse.model_validate(
        {
            "action": "edit",
            "edits": {"entry_trigger": "65200"},
        }
    )
    assert edited.model_dump(mode="json") == {
        "action": "edit",
        "edits": {"entry_trigger": "65200"},
    }
