from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.v2.build_normative_baseline import (
    build_initial_manifest,
    inspect_candidate_sources,
)


class NormativeBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self._git("init")
        self._git("config", "user.email", "baseline-test@example.invalid")
        self._git("config", "user.name", "Normative Baseline Test")
        self._write(
            "docs/approved.md",
            "# Approved\n\n"
            "> authority_class: approved_normative\n\n"
            "<!-- requirement: approved-one -->\n"
            "- MUST preserve the approved requirement.\n",
        )
        self._write(
            "docs/mixed.md",
            "# Mixed\n\n"
            "> authority_class: mixed\n>\n"
            "> normative_regions: D01,D02\n\n"
            "Informative opening.\n\n"
            "<!-- normative:start D01 -->\n"
            "<!-- requirement: mixed-one -->\n"
            "- MUST preserve mixed requirement one.\n"
            "<!-- normative:end D01 -->\n\n"
            "<!-- normative:start D02 -->\n"
            "<!-- requirement: mixed-two -->\n"
            "- MUST preserve mixed requirement two.\n"
            "<!-- normative:end D02 -->\n",
        )
        self._write(
            "docs/superseded.md",
            "# Superseded\n\n> authority_class: superseded\n",
        )
        self._write(
            "docs/proposed.md",
            "# Proposed gate\n\n"
            "> authority_class: proposed_gate\n\n"
            "<!-- requirement: hosted-recovery -->\n"
            "- MUST prove hosted recovery.\n",
        )
        self.policy_path = "docs/normative-source-policy.json"
        self.policy = {
            "schema_version": "1.0",
            "sources": [
                {
                    "path": "docs/approved.md",
                    "classification": "approved_normative",
                    "precedence": 10,
                },
                {
                    "path": "docs/mixed.md",
                    "classification": "mixed",
                    "precedence": 20,
                    "normative_regions": [
                        {"anchor": "D01"},
                        {"anchor": "D02"},
                    ],
                },
                {
                    "path": "docs/superseded.md",
                    "classification": "superseded",
                    "precedence": 30,
                    "superseded_by": "docs/approved.md",
                },
                {
                    "path": "docs/proposed.md",
                    "classification": "proposed_gate",
                    "precedence": 40,
                },
            ],
        }
        self._write_json(self.policy_path, self.policy)
        self._git("add", "docs")
        self._git("commit", "-m", "normative candidate")
        self.candidate_sha = self._git_output("rev-parse", "HEAD")
        self.review_note_path = "docs/review-evidence.md"
        self.review_note = "# Ordered review evidence\n\nAll three reviews approved.\n"
        self._write(self.review_note_path, self.review_note)
        self.review_note_sha = sha256(self.review_note.encode("utf-8")).hexdigest()
        self.review_chain = [
            self._review("specification_authority", "reviewer-spec", 1),
            self._review("plan_executability", "reviewer-plan", 2),
            self._review("official_framework", "reviewer-framework", 3),
        ]

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_builds_generation_one_from_candidate_blobs(self) -> None:
        manifest = self._build()

        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["generation"], 1)
        self.assertEqual(manifest["normative_sha"], self.candidate_sha)
        self.assertEqual(manifest["review_chain"], self.review_chain)
        self.assertEqual(
            manifest["review_evidence"],
            {
                "path": self.review_note_path,
                "sha256": self.review_note_sha,
            },
        )
        self.assertEqual(
            [item["path"] for item in manifest["files"]],
            sorted(item["path"] for item in self.policy["sources"]),
        )
        mixed = next(
            item for item in manifest["files"] if item["path"] == "docs/mixed.md"
        )
        self.assertEqual(
            mixed["normative_regions"], [{"anchor": "D01"}, {"anchor": "D02"}]
        )
        superseded = next(
            item
            for item in manifest["files"]
            if item["path"] == "docs/superseded.md"
        )
        self.assertEqual(superseded["superseded_by"], "docs/approved.md")
        approved = next(
            item
            for item in manifest["files"]
            if item["path"] == "docs/approved.md"
        )
        self.assertEqual(
            approved["sha256"],
            sha256((self.root / "docs/approved.md").read_bytes()).hexdigest(),
        )

    def test_reads_policy_and_sources_from_candidate_not_worktree(self) -> None:
        self._write_json(self.policy_path, {"schema_version": "1.0", "sources": []})
        self._write(
            "docs/approved.md",
            "# Worktree tamper\n\n> authority_class: informative\n",
        )

        manifest = self._build()

        self.assertEqual(len(manifest["files"]), 4)
        approved = next(
            item
            for item in manifest["files"]
            if item["path"] == "docs/approved.md"
        )
        candidate_blob = subprocess.run(
            ["git", "show", f"{self.candidate_sha}:docs/approved.md"],
            cwd=self.root,
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(approved["sha256"], sha256(candidate_blob).hexdigest())

        snapshot = inspect_candidate_sources(
            candidate_sha=self.candidate_sha,
            source_policy_path=self.policy_path,
            repo_root=self.root,
        )
        self.assertEqual(snapshot["candidate_sha"], self.candidate_sha)
        self.assertEqual(len(snapshot["files"]), 4)

    def test_rejects_policy_declaration_and_region_drift(self) -> None:
        drifted = json.loads(json.dumps(self.policy))
        drifted["sources"][0]["classification"] = "informative"
        self._commit_policy(drifted, "classification drift")
        with self.assertRaisesRegex(ValueError, "authority_class"):
            self._build()

        missing_region = json.loads(json.dumps(self.policy))
        missing_region["sources"][1]["normative_regions"].append(
            {"anchor": "D03"}
        )
        self._commit_policy(missing_region, "region drift")
        with self.assertRaisesRegex(ValueError, "normative_regions"):
            self._build()

    def test_rejects_incomplete_reviews_and_invalid_supersession(self) -> None:
        with self.assertRaisesRegex(ValueError, "all three required reviews"):
            self._build(review_chain=self.review_chain[:2])

        invalid = json.loads(json.dumps(self.policy))
        invalid["sources"][2]["superseded_by"] = "docs/missing.md"
        self._commit_policy(invalid, "invalid supersession")
        with self.assertRaisesRegex(ValueError, "superseded_by"):
            self._build()

    def test_cli_reads_candidate_policy_and_refuses_overwrite(self) -> None:
        self._write_json(self.policy_path, {"schema_version": "1.0", "sources": []})
        review_chain_path = self.root / "review-chain.json"
        self._write_json(
            str(review_chain_path.relative_to(self.root)),
            {"review_chain": self.review_chain},
        )
        output = self.root / "docs/normative-baseline.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "build_normative_baseline.py"),
            "--candidate-sha",
            self.candidate_sha,
            "--source-policy",
            self.policy_path,
            "--review-chain",
            str(review_chain_path),
            "--review-note",
            str(self.root / self.review_note_path),
            "--output",
            str(output),
        ]

        first = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already exists", second.stderr)

    def test_cli_preflights_sources_without_review_claims(self) -> None:
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "build_normative_baseline.py"),
            "--candidate-sha",
            self.candidate_sha,
            "--source-policy",
            self.policy_path,
            "--check-sources",
        ]

        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot["candidate_sha"], self.candidate_sha)
        self.assertEqual(len(snapshot["files"]), 4)

    def _build(self, review_chain: list[dict[str, object]] | None = None):
        return build_initial_manifest(
            candidate_sha=self.candidate_sha,
            source_policy_path=self.policy_path,
            review_chain=review_chain or self.review_chain,
            repo_root=self.root,
            review_evidence_sha256=self.review_note_sha,
            review_evidence_path=self.review_note_path,
            generated_at=datetime(2026, 7, 17, 2, 0, tzinfo=UTC),
        )

    def _commit_policy(self, policy: object, message: str) -> None:
        self._write_json(self.policy_path, policy)
        self._git("add", self.policy_path)
        self._git("commit", "-m", message)
        self.candidate_sha = self._git_output("rev-parse", "HEAD")
        self.review_chain = [
            self._review("specification_authority", "reviewer-spec", 1),
            self._review("plan_executability", "reviewer-plan", 2),
            self._review("official_framework", "reviewer-framework", 3),
        ]

    def _review(self, role: str, reviewer: str, sequence: int) -> dict[str, object]:
        return {
            "role": role,
            "reviewer": reviewer,
            "result": "approved",
            "critical_findings": 0,
            "important_findings": 0,
            "sequence": sequence,
            "reviewed_at": f"2026-07-17T01:0{sequence}:00Z",
            "candidate_sha": self.candidate_sha,
            "evidence_path": self.review_note_path,
            "evidence_sha256": self.review_note_sha,
            "scope": f"Task 0 governance review for {role}",
            "command": f"review-tool --role {role} --candidate {self.candidate_sha}",
        }

    def _write(self, path: str, content: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)

    def _write_json(self, path: str, value: object) -> None:
        self._write(
            path,
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def _git(self, *args: str) -> None:
        subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True
        )

    def _git_output(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()


if __name__ == "__main__":
    unittest.main()
