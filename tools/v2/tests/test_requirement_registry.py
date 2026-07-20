from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.v2.build_requirement_registry import (
    build_registry,
    build_source_requirements,
    registry_sha256,
    transition_registry_gate,
    validate_registry,
)
from tools.v2.transition_normative_baseline import transition_manifest
from tools.v2.verify_requirements import (
    assign_owner,
    build_pre_red_receipt,
    create_pre_red_receipt,
    reset_owner,
    verify_candidate_index,
    verify_pre_red_receipt,
)


NORMATIVE_SHA = "a" * 40
REVIEWED_SHA = "b" * 40
TASK_RED_COMMAND = "python3.12 tools/v2/tests/test_requirement_registry.py"
TASK_GREEN_COMMAND = "python3.12 tools/v2/tests/test_requirement_registry.py"


class RequirementRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        docs = self.root / "docs"
        docs.mkdir()
        self._write(
            "docs/approved.md",
            "# Approved\n\n"
            "<!-- requirement: tenant-isolation -->\n"
            "- MUST isolate tenant records.\n"
            "<!-- requirement: cited-urls -->\n"
            "- MUST preserve cited URLs.\n",
        )
        self._write(
            "docs/mixed.md",
            "# Mixed\n\n- Informative introduction.\n"
            "<!-- normative:start D01 -->\n"
            "<!-- requirement: typed-task-projection -->\n"
            "- MUST expose a typed task projection.\n"
            "<!-- normative:end D01 -->\n"
            "- Informative appendix.\n",
        )
        self._write(
            "docs/proposed.md",
            "# Deployment gate\n\n"
            "<!-- requirement: restart-recovery -->\n"
            "- MUST prove restart recovery in production.\n",
        )
        self._write(
            "docs/informative.md",
            "# Notes\n\n- MUST NOT become a normative requirement.\n",
        )
        self.manifest = {
            "schema_version": "1.0",
            "generation": 1,
            "normative_sha": NORMATIVE_SHA,
            "generated_at": "2026-07-17T00:00:00Z",
            "files": [
                self._manifest_file("docs/approved.md", "approved_normative"),
                {
                    **self._manifest_file("docs/mixed.md", "mixed"),
                    "normative_regions": [{"anchor": "D01"}],
                },
                self._manifest_file("docs/proposed.md", "proposed_gate"),
                self._manifest_file("docs/informative.md", "informative"),
            ],
            "review_chain": [],
        }

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_sources_include_only_normative_regions_and_proposed_gates(self) -> None:
        sources = build_source_requirements(self.manifest, root=self.root)

        statements = {item["statement"] for item in sources}
        self.assertEqual(
            statements,
            {
                "MUST isolate tenant records.",
                "MUST preserve cited URLs.",
                "MUST expose a typed task projection.",
                "MUST prove restart recovery in production.",
            },
        )
        self.assertEqual(len({item["id"] for item in sources}), len(sources))
        self.assertTrue(all(item["id"].endswith("-v1") for item in sources))
        proposed = next(
            item for item in sources if item["classification"] == "proposed_gate"
        )
        self.assertEqual(proposed["kind"], "gate")
        self.assertEqual(proposed["source_anchor"], "root:restart-recovery")

    def test_normative_statement_without_explicit_anchor_fails_closed(self) -> None:
        self._write(
            "docs/approved.md",
            "# Approved\n\n- MUST isolate tenant records.\n",
        )
        self.manifest["files"][0] = self._manifest_file(
            "docs/approved.md", "approved_normative"
        )

        with self.assertRaisesRegex(ValueError, "explicit requirement anchor"):
            build_source_requirements(self.manifest, root=self.root)

    def test_duplicate_requirement_anchor_fails_closed(self) -> None:
        self._write(
            "docs/approved.md",
            "# Approved\n\n"
            "<!-- requirement: tenant-isolation -->\n"
            "- MUST isolate tenant records.\n"
            "<!-- requirement: tenant-isolation -->\n"
            "- MUST preserve cited URLs.\n",
        )
        self.manifest["files"][0] = self._manifest_file(
            "docs/approved.md", "approved_normative"
        )

        with self.assertRaisesRegex(ValueError, "duplicate requirement anchor"):
            build_source_requirements(self.manifest, root=self.root)

    def test_registry_builder_requires_complete_explicit_mappings(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit reviewed mapping"):
            build_registry(self.manifest, root=self.root)

        incomplete = self._complete_registry()
        incomplete["requirements"].pop()
        with self.assertRaisesRegex(ValueError, "explicit reviewed mapping"):
            build_registry(self.manifest, root=self.root, existing=incomplete)

        complete = self._complete_registry()
        generated = build_registry(self.manifest, root=self.root, existing=complete)
        validate_registry(generated, self.manifest, root=self.root)

    def test_registry_hash_is_deterministic_across_mapping_key_order(self) -> None:
        complete = self._complete_registry()
        reordered = deepcopy(complete)
        reordered["requirements"] = [
            dict(reversed(list(entry.items()))) for entry in reordered["requirements"]
        ]

        first = build_registry(self.manifest, root=self.root, existing=complete)
        second = build_registry(self.manifest, root=self.root, existing=reordered)
        self.assertEqual(registry_sha256(first), registry_sha256(second))
        reordered_registry = deepcopy(first)
        reordered_registry["requirements"].reverse()
        with self.assertRaisesRegex(ValueError, "requirement order"):
            validate_registry(reordered_registry, self.manifest, root=self.root)

    def test_registry_rejects_reviewed_source_drift(self) -> None:
        registry = self._complete_registry()
        self._write(
            "docs/approved.md",
            "# Approved\n\n"
            "<!-- requirement: tenant-isolation -->\n"
            "- MUST isolate all tenant records.\n"
            "<!-- requirement: cited-urls -->\n"
            "- MUST preserve cited URLs.\n",
        )
        self.manifest["files"][0] = self._manifest_file(
            "docs/approved.md", "approved_normative"
        )

        with self.assertRaisesRegex(ValueError, "does not match manifest field"):
            validate_registry(registry, self.manifest, root=self.root)
        with self.assertRaisesRegex(ValueError, "source drift"):
            build_registry(self.manifest, root=self.root, existing=registry)

    def test_registry_builder_rejects_removed_source_mappings(self) -> None:
        registry = self._complete_registry()
        self.manifest["files"] = [
            item
            for item in self.manifest["files"]
            if item["path"] != "docs/approved.md"
        ]

        with self.assertRaisesRegex(ValueError, "removed requirements"):
            build_registry(self.manifest, root=self.root, existing=registry)

    def test_registry_requires_every_child_and_rejects_catch_all_replacement(
        self,
    ) -> None:
        registry = self._complete_registry()
        validate_registry(registry, self.manifest, root=self.root)

        missing_child = deepcopy(registry)
        missing_child["requirements"].pop(0)
        missing_child["requirements"].append(
            {
                **registry["requirements"][0],
                "id": "V2-REQ-docs-approved-meta-v1",
                "source_anchor": "root:*",
                "statement_sha256": sha256(b"all requirements").hexdigest(),
            }
        )

        with self.assertRaisesRegex(ValueError, "missing requirement IDs"):
            validate_registry(missing_child, self.manifest, root=self.root)

    def test_registry_rejects_invalid_proof_and_owner_placeholders(self) -> None:
        registry = self._complete_registry()
        proposed = next(
            item
            for item in registry["requirements"]
            if item["classification"] == "proposed_gate"
        )
        proposed["final_proof_target"] = "local-contract"
        proposed["required_environment"] = "local"

        with self.assertRaisesRegex(ValueError, "hosted-production"):
            validate_registry(registry, self.manifest, root=self.root)

        proposed["final_proof_target"] = "hosted-production"
        proposed["required_environment"] = "hosted-production"
        registry["requirements"][0]["accountable_role"] = "shared-owner"
        with self.assertRaisesRegex(ValueError, "accountable_role"):
            validate_registry(registry, self.manifest, root=self.root)

    def test_owner_assignment_builds_and_verifies_immutable_pre_red_receipt(
        self,
    ) -> None:
        registry = self._complete_registry()
        assigned_at = datetime(2026, 7, 17, 1, 0, tzinfo=UTC)
        assigned = assign_owner(
            registry,
            task=1,
            agent_id="agent-task-01-alpha",
            assigned_at=assigned_at,
        )
        with self.assertRaisesRegex(ValueError, "frozen intended RED command"):
            build_pre_red_receipt(
                assigned,
                task=1,
                red_command="pytest tests/contract/unreviewed_command.py",
                created_at=assigned_at + timedelta(seconds=1),
            )
        receipt = build_pre_red_receipt(
            assigned,
            task=1,
            red_command=TASK_RED_COMMAND,
            created_at=assigned_at + timedelta(seconds=1),
        )

        verify_pre_red_receipt(
            assigned,
            receipt,
            task=1,
            expected_red_command=TASK_RED_COMMAND,
        )
        forged_receipt = deepcopy(receipt)
        forged_receipt["red_command"] = "pytest tests/contract/forged.py"
        with self.assertRaisesRegex(ValueError, "frozen command"):
            verify_pre_red_receipt(
                assigned,
                forged_receipt,
                task=1,
                expected_red_command="pytest tests/contract/forged.py",
            )
        self.assertEqual(receipt["registry_sha256"], registry_sha256(assigned))
        self.assertEqual(
            {item["agent_id"] for item in receipt["owner_assignments"]},
            {"agent-task-01-alpha"},
        )

        tampered = deepcopy(assigned)
        tampered["requirements"][0]["owner_agent_id"] = "agent-attacker"
        with self.assertRaisesRegex(ValueError, "registry hash"):
            verify_pre_red_receipt(
                tampered,
                receipt,
                task=1,
                expected_red_command=TASK_RED_COMMAND,
            )

        reset = reset_owner(
            assigned,
            task=1,
            expected_agent_id="agent-task-01-alpha",
        )
        self.assertTrue(
            all(
                item["owner_agent_id"] is None
                for item in reset["requirements"]
                if item["implementation_task"] == 1
            )
        )

    def test_pre_red_receipt_is_created_exclusively(self) -> None:
        registry = assign_owner(
            self._complete_registry(),
            task=1,
            agent_id="agent-task-01-alpha",
            assigned_at=datetime(2026, 7, 17, 1, 0, tzinfo=UTC),
        )
        receipt_path = self.root / "artifacts/v2-final/pre-red/task-1.json"
        receipt = create_pre_red_receipt(
            registry,
            receipt_path=receipt_path,
            task=1,
            red_command=TASK_RED_COMMAND,
            created_at=datetime(2026, 7, 17, 1, 0, 1, tzinfo=UTC),
        )

        self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8")), receipt)
        with self.assertRaisesRegex(ValueError, "already exists"):
            create_pre_red_receipt(
                registry,
                receipt_path=receipt_path,
                task=1,
                red_command=TASK_RED_COMMAND,
                created_at=datetime(2026, 7, 17, 1, 0, 2, tzinfo=UTC),
            )

    def test_pre_red_cli_creates_then_only_verifies_existing_receipt(self) -> None:
        registry = assign_owner(
            self._complete_registry(),
            task=1,
            agent_id="agent-task-01-alpha",
            assigned_at=datetime(2026, 7, 17, 1, 0, tzinfo=UTC),
        )
        manifest_path = self.root / "docs/v2/normative-baseline.json"
        registry_path = self.root / "docs/v2/requirements-registry.yaml"
        receipt_path = self.root / "artifacts/v2-final/pre-red/task-1.json"
        self._write_json(manifest_path, self.manifest)
        self._write_json(registry_path, registry)
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "verify_requirements.py"),
            "--registry",
            str(registry_path),
            "--manifest",
            str(manifest_path),
            "--phase",
            "pre-red",
            "--task",
            "1",
            "--receipt",
            str(receipt_path),
            "--red-command",
            TASK_RED_COMMAND,
        ]

        subprocess.run(command, cwd=self.root, check=True, capture_output=True)
        original = receipt_path.read_bytes()
        subprocess.run(command, cwd=self.root, check=True, capture_output=True)
        self.assertEqual(receipt_path.read_bytes(), original)

    def test_governance_cli_rejects_an_empty_review_chain(self) -> None:
        registry = self._complete_registry()
        manifest_path = self.root / "docs/v2/normative-baseline.json"
        registry_path = self.root / "docs/v2/requirements-registry.yaml"
        self._write_json(manifest_path, self.manifest)
        self._write_json(registry_path, registry)
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "verify_requirements.py"),
                "--registry",
                str(registry_path),
                "--manifest",
                str(manifest_path),
                "--phase",
                "governance-transition",
                "--require-normative-sha",
                NORMATIVE_SHA,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ordered review chain", result.stderr)

    def test_candidate_verification_reads_staged_blobs_and_notes(self) -> None:
        self._git("init")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Requirement Registry Test")
        self._git("add", "docs")
        self._git("commit", "-m", "normative baseline")
        self.manifest["normative_sha"] = self._git_output("rev-parse", "HEAD")
        registry = assign_owner(
            self._complete_registry(),
            task=1,
            agent_id="agent-task-01-alpha",
            assigned_at=datetime(2026, 7, 17, 1, 0, tzinfo=UTC),
        )
        receipt = build_pre_red_receipt(
            registry,
            task=1,
            red_command=TASK_RED_COMMAND,
            created_at=datetime(2026, 7, 17, 1, 0, 1, tzinfo=UTC),
        )
        note_path = Path("docs/v2/implementation/2026-07-17-task-01.md")
        manifest_path = self.root / "docs/v2/normative-baseline.json"
        registry_path = self.root / "docs/v2/requirements-registry.yaml"
        receipt_path = self.root / "artifacts/v2-final/pre-red/task-1.json"
        self._write_json(manifest_path, self.manifest)
        self._write_json(registry_path, registry)
        self._write_json(receipt_path, receipt)
        self._git("add", str(manifest_path.relative_to(self.root)))
        self._git("commit", "-m", "normative baseline attestation")
        self._write(str(note_path), self._implementation_note(registry, note_path))
        self._git("add", str(registry_path.relative_to(self.root)))
        self._git("add", str(receipt_path.relative_to(self.root)))
        self._git("add", str(note_path))

        registry_path.write_text("{}\n", encoding="utf-8")
        receipt_path.write_text("{}\n", encoding="utf-8")
        self._write(
            "docs/approved.md",
            "# Worktree-only tamper\n\n- This must not affect index verification.\n",
        )
        self._write(str(note_path), "assigned-before-red\n")
        verify_candidate_index(
            registry_path=registry_path,
            manifest_path=manifest_path,
            receipt_path=receipt_path,
            task=1,
            expected_red_command=TASK_RED_COMMAND,
            repo_root=self.root,
        )

        registry_path.unlink()
        (self.root / "alternate-registry.json").write_text("{}\n", encoding="utf-8")
        registry_path.symlink_to("../../alternate-registry.json")
        verify_candidate_index(
            registry_path=registry_path,
            manifest_path=manifest_path,
            receipt_path=receipt_path,
            task=1,
            expected_red_command=TASK_RED_COMMAND,
            repo_root=self.root,
        )

        self._write(
            str(note_path),
            f"{registry['normative_sha']} agent-task-01-alpha "
            + " ".join(str(item["id"]) for item in registry["requirements"]),
        )
        self._git("add", str(note_path))
        with self.assertRaisesRegex(ValueError, "metadata block"):
            verify_candidate_index(
                registry_path=registry_path,
                manifest_path=manifest_path,
                receipt_path=receipt_path,
                task=1,
                expected_red_command=TASK_RED_COMMAND,
                repo_root=self.root,
            )
        self._write(str(note_path), self._implementation_note(registry, note_path))
        self._git("add", str(note_path))

        self._git("add", str(receipt_path.relative_to(self.root)))
        with self.assertRaisesRegex(ValueError, "pre-RED receipt schema"):
            verify_candidate_index(
                registry_path=registry_path,
                manifest_path=manifest_path,
                receipt_path=receipt_path,
                task=1,
                expected_red_command=TASK_RED_COMMAND,
                repo_root=self.root,
            )

        forged_manifest = deepcopy(self.manifest)
        forged_manifest["files"] = [
            item
            for item in forged_manifest["files"]
            if item["path"] != "docs/approved.md"
        ]
        forged_registry = deepcopy(registry)
        forged_registry["requirements"] = [
            item
            for item in forged_registry["requirements"]
            if item["source_path"] != "docs/approved.md"
        ]
        registry_path.unlink()
        self._write_json(manifest_path, forged_manifest)
        self._write_json(registry_path, forged_registry)
        self._git("add", str(manifest_path.relative_to(self.root)))
        self._git("add", str(registry_path.relative_to(self.root)))
        with self.assertRaisesRegex(ValueError, "must not modify normative-baseline"):
            verify_candidate_index(
                registry_path=registry_path,
                manifest_path=manifest_path,
                receipt_path=receipt_path,
                task=1,
                expected_red_command=TASK_RED_COMMAND,
                repo_root=self.root,
            )

    def test_gate_transition_requires_ordered_reviews_and_preserves_ids(self) -> None:
        self._git("init")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Requirement Registry Test")
        self._git("add", "docs")
        self._git("commit", "-m", "normative baseline")
        self.manifest["normative_sha"] = self._git_output("rev-parse", "HEAD")
        registry = self._complete_registry()
        self._git("commit", "--allow-empty", "-m", "reviewed governance candidate")
        reviewed_sha = self._git_output("rev-parse", "HEAD")
        review_note_path = "docs/review-evidence.md"
        review_note = "# Ordered review evidence\n\nAll three reviews approved.\n"
        self._write(review_note_path, review_note)
        review_note_sha = sha256(review_note.encode("utf-8")).hexdigest()
        reviews = [
            self._review(
                "specification_authority",
                "reviewer-spec",
                1,
                reviewed_sha,
                review_note_path,
                review_note_sha,
            ),
            self._review(
                "plan_executability",
                "reviewer-plan",
                2,
                reviewed_sha,
                review_note_path,
                review_note_sha,
            ),
            self._review(
                "official_framework",
                "reviewer-framework",
                3,
                reviewed_sha,
                review_note_path,
                review_note_sha,
            ),
        ]
        transitioned_manifest = transition_manifest(
            self.manifest,
            promote_path="docs/proposed.md",
            candidate_sha=reviewed_sha,
            review_chain=reviews,
            repo_root=self.root,
            review_evidence_sha256=review_note_sha,
            review_evidence_path=review_note_path,
            generated_at=datetime(2026, 7, 17, 2, 0, tzinfo=UTC),
        )
        transitioned_registry = transition_registry_gate(
            registry,
            previous_manifest=self.manifest,
            next_manifest=transitioned_manifest,
            promoted_path="docs/proposed.md",
            root=self.root,
        )

        before = {
            item["statement_sha256"]: item["id"]
            for item in registry["requirements"]
            if item["source_path"] == "docs/proposed.md"
        }
        after = {
            item["statement_sha256"]: item["id"]
            for item in transitioned_registry["requirements"]
            if item["source_path"] == "docs/proposed.md"
        }
        self.assertEqual(before, after)
        self.assertTrue(
            all(
                item["kind"] == "normative"
                and item["classification"] == "approved_normative"
                for item in transitioned_registry["requirements"]
                if item["source_path"] == "docs/proposed.md"
            )
        )
        self.assertEqual(transitioned_registry["normative_sha"], reviewed_sha)

        with self.assertRaisesRegex(ValueError, "ordered review chain"):
            transition_manifest(
                self.manifest,
                promote_path="docs/proposed.md",
                candidate_sha=reviewed_sha,
                review_chain=reviews[:2],
                repo_root=self.root,
                review_evidence_sha256=review_note_sha,
                review_evidence_path=review_note_path,
                generated_at=datetime(2026, 7, 17, 2, 0, tzinfo=UTC),
            )

        missing_candidate = deepcopy(reviews)
        missing_candidate[1].pop("candidate_sha")
        with self.assertRaisesRegex(ValueError, "candidate SHA"):
            transition_manifest(
                self.manifest,
                promote_path="docs/proposed.md",
                candidate_sha=reviewed_sha,
                review_chain=missing_candidate,
                repo_root=self.root,
                review_evidence_sha256=review_note_sha,
                review_evidence_path=review_note_path,
                generated_at=datetime(2026, 7, 17, 2, 0, tzinfo=UTC),
            )

        with self.assertRaisesRegex(ValueError, "repository commit"):
            transition_manifest(
                self.manifest,
                promote_path="docs/proposed.md",
                candidate_sha=REVIEWED_SHA,
                review_chain=reviews,
                repo_root=self.root,
                review_evidence_sha256=review_note_sha,
                review_evidence_path=review_note_path,
                generated_at=datetime(2026, 7, 17, 2, 0, tzinfo=UTC),
            )

    def test_documented_transition_clis_update_manifest_and_registry(self) -> None:
        self._git("init")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Requirement Registry Test")
        self._git("add", "docs")
        self._git("commit", "-m", "normative candidate")
        self.manifest["normative_sha"] = self._git_output("rev-parse", "HEAD")
        manifest_path = self.root / "docs/v2/normative-baseline.json"
        registry_path = self.root / "docs/v2/requirements-registry.yaml"
        self._write_json(manifest_path, self.manifest)
        self._write_json(registry_path, self._complete_registry())
        self._git("add", str(manifest_path.relative_to(self.root)))
        self._git("add", str(registry_path.relative_to(self.root)))
        self._git("commit", "-m", "attest normative baseline")
        self._git("commit", "--allow-empty", "-m", "governance candidate")
        candidate_sha = self._git_output("rev-parse", "HEAD")
        review_note_path = self.root / "docs/review-evidence.md"
        review_note = "# Ordered review evidence\n\nAll reviews approved.\n"
        review_note_path.write_text(review_note, encoding="utf-8")
        review_note_sha = sha256(review_note.encode("utf-8")).hexdigest()
        review_chain = [
            self._review(
                role,
                reviewer,
                sequence,
                candidate_sha,
                str(review_note_path.relative_to(self.root)),
                review_note_sha,
            )
            for sequence, (role, reviewer) in enumerate(
                (
                    ("specification_authority", "reviewer-spec"),
                    ("plan_executability", "reviewer-plan"),
                    ("official_framework", "reviewer-framework"),
                ),
                start=1,
            )
        ]
        review_chain_path = self.root / "review-chain.json"
        self._write_json(review_chain_path, {"review_chain": review_chain})
        tools_dir = Path(__file__).resolve().parents[1]

        transition_result = subprocess.run(
            [
                sys.executable,
                str(tools_dir / "transition_normative_baseline.py"),
                "--current-manifest",
                str(manifest_path),
                "--candidate-sha",
                candidate_sha,
                "--promote",
                "docs/proposed.md",
                "--review-chain",
                str(review_chain_path),
                "--review-note",
                str(review_note_path),
                "--output",
                str(manifest_path),
            ],
            cwd=self.root,
            check=False,
            capture_output=True,
        )
        self.assertEqual(
            transition_result.returncode,
            0,
            transition_result.stderr.decode("utf-8", "replace"),
        )
        registry_result = subprocess.run(
            [
                sys.executable,
                str(tools_dir / "build_requirement_registry.py"),
                "--manifest",
                str(manifest_path),
                "--registry",
                str(registry_path),
                "--transition-gate",
                "docs/proposed.md",
                "--check",
            ],
            cwd=self.root,
            check=False,
            capture_output=True,
        )
        self.assertEqual(
            registry_result.returncode,
            0,
            registry_result.stderr.decode("utf-8", "replace"),
        )
        subprocess.run(
            [
                sys.executable,
                str(tools_dir / "verify_requirements.py"),
                "--registry",
                str(registry_path),
                "--manifest",
                str(manifest_path),
                "--phase",
                "governance-transition",
                "--require-normative-sha",
                candidate_sha,
            ],
            cwd=self.root,
            check=True,
            capture_output=True,
        )

        transitioned = json.loads(registry_path.read_text(encoding="utf-8"))
        self.assertEqual(transitioned["normative_sha"], candidate_sha)
        self.assertTrue(
            all(
                item["classification"] == "approved_normative"
                for item in transitioned["requirements"]
                if item["source_path"] == "docs/proposed.md"
            )
        )

    def _complete_registry(self) -> dict[str, object]:
        requirements = build_source_requirements(self.manifest, root=self.root)
        entries = []
        for index, requirement in enumerate(requirements, start=1):
            hosted = requirement["classification"] == "proposed_gate"
            entries.append(
                {
                    **requirement,
                    "implementation_task": 1,
                    "implementation_slice": f"foundation-{index}",
                    "implementation_note_path": (
                        "docs/v2/implementation/2026-07-17-task-01.md"
                    ),
                    "accountable_role": "task_01_implementer",
                    "owner_agent_id": None,
                    "intended_red": {
                        "test": f"tests/contract/test_requirement_{index}.py",
                        "command": TASK_RED_COMMAND,
                        "expected_missing_behavior": "required behavior is absent",
                    },
                    "intended_green": {
                        "test": f"tests/contract/test_requirement_{index}.py",
                        "command": TASK_GREEN_COMMAND,
                    },
                    "proof_classification": "production" if hosted else "contract",
                    "final_proof_target": (
                        "hosted-production" if hosted else "local-contract"
                    ),
                    "required_environment": (
                        "hosted-production" if hosted else "local"
                    ),
                    "observed_evidence": {
                        "red": None,
                        "green": None,
                        "final": None,
                    },
                    "review_dispositions": {
                        "specification": None,
                        "code_quality": None,
                        "final_attestation": None,
                    },
                }
            )
        return {
            "schema_version": "1.0",
            "normative_sha": self.manifest["normative_sha"],
            "manifest_generation": self.manifest["generation"],
            "requirements": entries,
        }

    def _manifest_file(self, path: str, classification: str) -> dict[str, str]:
        return {
            "path": path,
            "classification": classification,
            "sha256": sha256((self.root / path).read_bytes()).hexdigest(),
        }

    def _review(
        self,
        role: str,
        reviewer: str,
        sequence: int,
        candidate_sha: str,
        evidence_path: str,
        evidence_sha256: str,
    ) -> dict[str, object]:
        return {
            "role": role,
            "reviewer": reviewer,
            "result": "approved",
            "critical_findings": 0,
            "important_findings": 0,
            "sequence": sequence,
            "reviewed_at": f"2026-07-17T01:0{sequence}:00Z",
            "candidate_sha": candidate_sha,
            "evidence_path": evidence_path,
            "evidence_sha256": evidence_sha256,
            "scope": f"Task 0 governance review for {role}",
            "command": f"review-tool --role {role} --candidate {candidate_sha}",
        }

    def _write(self, path: str, content: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _git(self, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )

    def _git_output(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _implementation_note(self, registry: dict[str, object], note_path: Path) -> str:
        requirement_ids = [
            str(item["id"])
            for item in registry["requirements"]
            if item["implementation_note_path"] == str(note_path)
        ]
        metadata = {
            "schema_version": "1.0",
            "slice_id": "task-01-foundation",
            "phase": "phase-1",
            "owner_role": "task_01_implementer",
            "owner_agent_id": "agent-task-01-alpha",
            "normative_sha": registry["normative_sha"],
            "base_sha": self._git_output("rev-parse", "HEAD"),
            "candidate_sha": None,
            "requirement_ids": requirement_ids,
            "status": "in_progress",
            "red": {
                "command": TASK_RED_COMMAND,
                "started_at": "2026-07-17T01:00:02Z",
                "exit_code": 1,
                "log_sha256": "d" * 64,
                "failure_classification": "required behavior was absent",
            },
            "green": {
                "command": TASK_GREEN_COMMAND,
                "exit_code": 0,
                "test_count": 14,
                "log_sha256": "e" * 64,
            },
            "real_evidence_limitations": (
                "Hosted production proof is outside this synthetic contract test."
            ),
        }
        return (
            "# Task 1 implementation note\n\n```json\n"
            + json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n```\n"
        )


if __name__ == "__main__":
    unittest.main()
