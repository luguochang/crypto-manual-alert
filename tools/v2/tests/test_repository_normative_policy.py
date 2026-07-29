from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.v2.build_normative_baseline import inspect_candidate_sources


REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = "docs/v2/normative-source-policy.json"


def _candidate_sha() -> str:
    explicit = os.environ.get("NORMATIVE_CANDIDATE_SHA")
    if explicit:
        return explicit
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_repository_normative_source_policy_matches_candidate() -> None:
    snapshot = inspect_candidate_sources(
        candidate_sha=_candidate_sha(),
        source_policy_path=POLICY_PATH,
        repo_root=REPO_ROOT,
    )
    files = snapshot["files"]

    assert len(files) == 27
    assert [item["path"] for item in files] == sorted(
        item["path"] for item in files
    )
    assert not any(item["classification"] == "proposed_gate" for item in files)

    by_path = {item["path"]: item for item in files}
    assert by_path["docs/v2/adr/0011-aegra-self-hosted-agent-server.md"][
        "classification"
    ] == "approved_normative"
    assert by_path["docs/v2/adr/0008-production-deployment-profile.md"] == {
        "path": "docs/v2/adr/0008-production-deployment-profile.md",
        "classification": "superseded",
        "precedence": 910,
        "sha256": by_path["docs/v2/adr/0008-production-deployment-profile.md"][
            "sha256"
        ],
        "superseded_by": "docs/v2/adr/0011-aegra-self-hosted-agent-server.md",
    }
    assert by_path["docs/v2/09-review-packet-and-decisions.md"][
        "normative_regions"
    ] == [{"anchor": f"D{index:02d}"} for index in range(1, 16)]
