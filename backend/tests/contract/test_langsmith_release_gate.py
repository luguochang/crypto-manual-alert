from dataclasses import replace

import pytest

from crypto_alert_v2.evaluation.dataset import (
    MINIMUM_RELEASE_CASE_NAMES,
    minimum_release_dataset,
    upload_minimum_dataset,
)
from crypto_alert_v2.evaluation.experiment import (
    run_official_langsmith_experiment,
    run_repeatable_offline_experiment,
)
from crypto_alert_v2.evaluation.release_gate import (
    assess_real_platform_credentials,
    evaluate_release_gate,
)


def _passing_result():
    return run_repeatable_offline_experiment(
        minimum_release_dataset(),
        target=lambda inputs: {"fixture": inputs["fixture"]},
        evaluator=lambda case, output: {
            "structure": 1.0,
            "evidence": 1.0,
            "risk": 1.0,
            "product_output": 1.0,
        },
        prompt_version="market-analysis-v1",
        git_revision="candidate-sha",
    )


def test_minimum_dataset_contains_every_normative_release_case() -> None:
    cases = minimum_release_dataset()

    assert tuple(case.name for case in cases) == MINIMUM_RELEASE_CASE_NAMES
    assert all(case.as_langsmith_example()["metadata"]["case_name"] for case in cases)


def test_repeatable_experiment_passes_all_release_metrics_with_version_linkage() -> (
    None
):
    result = _passing_result()

    report = evaluate_release_gate(result)

    assert report.approved is True
    assert report.reasons == ()
    assert report.prompt_version == "market-analysis-v1"
    assert report.git_revision == "candidate-sha"


def test_release_gate_blocks_metric_regression_and_missing_version() -> None:
    result = _passing_result()
    result.case_results[0].scores["evidence"] = 0.0
    degraded = replace(
        result,
        metrics={**result.metrics, "evidence": 0.8},
        prompt_version="",
    )

    report = evaluate_release_gate(degraded)

    assert report.approved is False
    assert "missing_prompt_version" in report.reasons
    assert any(
        reason.startswith("metric_below_threshold:evidence")
        for reason in report.reasons
    )


def test_real_platform_credentials_are_a_separate_hard_gate_not_a_skip() -> None:
    gate = assess_real_platform_credentials(
        langsmith_api_key=None,
        langsmith_project="crypto-alert-v2",
        langfuse_public_key=None,
        langfuse_secret_key=None,
    )

    assert gate.ready is False
    assert gate.missing == (
        "LANGSMITH_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    )
    with pytest.raises(RuntimeError, match="real observability gate is unavailable"):
        gate.require()


def test_official_langsmith_dataset_and_experiment_use_one_explicit_client() -> None:
    class Dataset:
        id = "dataset-id"

    class RecordingClient:
        def __init__(self) -> None:
            self.created_dataset = None
            self.created_examples = None
            self.evaluation = None

        def create_dataset(self, name, **kwargs):
            self.created_dataset = (name, kwargs)
            return Dataset()

        def create_examples(self, **kwargs):
            self.created_examples = kwargs
            return {"count": len(kwargs["examples"])}

        def evaluate(self, target, **kwargs):
            self.evaluation = (target, kwargs)
            return {"experiment_name": "release-proof"}

    client = RecordingClient()

    def target(inputs):
        return inputs

    dataset = upload_minimum_dataset(
        client,
        dataset_name="crypto-alert-v2-minimum",
        description="release dataset",
    )
    experiment = run_official_langsmith_experiment(
        target,
        dataset_name="crypto-alert-v2-minimum",
        evaluators=[lambda outputs, reference_outputs: {"score": 1.0}],
        client=client,
        experiment_prefix="candidate",
        prompt_version="market-analysis-v1",
        git_revision="candidate-sha",
    )

    assert dataset.id == "dataset-id"
    assert client.created_dataset == (
        "crypto-alert-v2-minimum",
        {"description": "release dataset"},
    )
    assert client.created_examples["dataset_id"] == "dataset-id"
    assert len(client.created_examples["examples"]) == 6
    assert client.evaluation[0] is target
    assert client.evaluation[1]["data"] == "crypto-alert-v2-minimum"
    assert client.evaluation[1]["metadata"] == {
        "prompt_version": "market-analysis-v1",
        "git_revision": "candidate-sha",
        "release_proof": True,
    }
    assert experiment == {"experiment_name": "release-proof"}
