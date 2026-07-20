#!/usr/bin/env python3
"""Verify registry ownership and immutable pre-RED receipts."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

try:
    from tools.v2.build_requirement_registry import (
        load_document,
        registry_sha256,
        validate_registry,
        write_document,
    )
except ModuleNotFoundError:  # Direct execution from tools/v2.
    from build_requirement_registry import (  # type: ignore[no-redef]
        load_document,
        registry_sha256,
        validate_registry,
        write_document,
    )


AGENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{2,127}$")
PLACEHOLDER = re.compile(
    r"(?:\btbd\b|\btodo\b|placeholder|unknown|unassigned|shared[-_ ]owner|"
    r"catch[-_ ]all|dummy|fake|example[-_ ]only)",
    re.IGNORECASE,
)
NOTE_TEMPLATE_SENTINELS = (
    "assigned-before-red",
    "immutable-task-0-candidate-sha",
    "sha-before-red",
    "V2-REQ-source-stable-id",
    "in_progress|verified|blocked",
)
NOTE_METADATA_BLOCK = re.compile(
    r"```(?:json|yaml)\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


def _parse_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a timezone-aware ISO-8601 timestamp")
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{name} must be a timezone-aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware ISO-8601 timestamp")
    return parsed.astimezone(UTC)


def _timestamp(value: datetime | None) -> str:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return current.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _concrete_agent_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or PLACEHOLDER.search(value):
        raise ValueError("agent_id must be a concrete non-placeholder Agent ID")
    value = value.strip()
    if not AGENT_ID.fullmatch(value):
        raise ValueError("agent_id must be a concrete non-placeholder Agent ID")
    return value


def _task_requirements(registry: Mapping[str, Any], task: int) -> list[dict[str, Any]]:
    if not isinstance(task, int) or isinstance(task, bool) or task < 1:
        raise ValueError("task must be a positive integer")
    requirements = registry.get("requirements")
    if not isinstance(requirements, list):
        raise ValueError("registry requirements must be a list")
    selected = [
        dict(item)
        for item in requirements
        if isinstance(item, Mapping) and item.get("implementation_task") == task
    ]
    if not selected:
        raise ValueError(f"registry has no requirements for task {task}")
    return selected


def assign_owner(
    registry: Mapping[str, Any],
    *,
    task: int,
    agent_id: str,
    assigned_at: datetime | None = None,
) -> dict[str, Any]:
    """Assign exactly one concrete Agent ID to every requirement owned by a task."""

    owner = _concrete_agent_id(agent_id)
    selected = _task_requirements(registry, task)
    assigned_time = _timestamp(assigned_at)
    result = deepcopy(dict(registry))
    changed = 0
    for raw_entry in result["requirements"]:
        if (
            not isinstance(raw_entry, Mapping)
            or raw_entry.get("implementation_task") != task
        ):
            continue
        existing = raw_entry.get("owner_agent_id")
        if existing not in (None, owner):
            raise ValueError(
                f"requirement {raw_entry.get('id')} already belongs to another Agent ID"
            )
        raw_entry["owner_agent_id"] = owner
        raw_entry["owner_assigned_at"] = assigned_time
        changed += 1
    if changed != len(selected):
        raise ValueError("owner assignment did not cover every task requirement")
    return result


def reset_owner(
    registry: Mapping[str, Any],
    *,
    task: int,
    expected_agent_id: str,
) -> dict[str, Any]:
    """Reset only the concrete disposable assignment owned by ``expected_agent_id``."""

    expected = _concrete_agent_id(expected_agent_id)
    selected = _task_requirements(registry, task)
    result = deepcopy(dict(registry))
    for raw_entry in result["requirements"]:
        if (
            not isinstance(raw_entry, Mapping)
            or raw_entry.get("implementation_task") != task
        ):
            continue
        if raw_entry.get("owner_agent_id") != expected:
            raise ValueError(
                f"requirement {raw_entry.get('id')} is not owned by expected Agent ID"
            )
        raw_entry["owner_agent_id"] = None
        raw_entry.pop("owner_assigned_at", None)
    if not selected:
        raise ValueError(f"registry has no requirements for task {task}")
    return result


def _receipt_assignments(
    registry: Mapping[str, Any],
    selected: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    assignments: list[dict[str, Any]] = []
    agents: set[str] = set()
    for entry in selected:
        identifier = entry.get("id")
        agent = _concrete_agent_id(entry.get("owner_agent_id"))
        assigned_at = _parse_timestamp(
            entry.get("owner_assigned_at"),
            f"requirement {identifier}.owner_assigned_at",
        )
        agents.add(agent)
        assignments.append(
            {
                "requirement_id": identifier,
                "accountable_role": entry.get("accountable_role"),
                "agent_id": agent,
                "assigned_at": _timestamp(assigned_at),
            }
        )
    if len(agents) != 1:
        raise ValueError("pre-RED receipt requires one Agent ID for the whole task")
    assignments.sort(key=lambda item: item["requirement_id"])
    return assignments, next(iter(agents))


def build_pre_red_receipt(
    assigned_registry: Mapping[str, Any],
    *,
    task: int,
    red_command: str,
    created_at: datetime | None = None,
    red_started_at: datetime | None = None,
) -> dict[str, Any]:
    """Build an immutable receipt for the exact registry about to enter RED."""

    if (
        not isinstance(red_command, str)
        or not red_command.strip()
        or PLACEHOLDER.search(red_command)
    ):
        raise ValueError("red_command must be concrete and non-placeholder")
    selected = _task_requirements(assigned_registry, task)
    assignments, agent = _receipt_assignments(assigned_registry, selected)
    created = _timestamp(created_at)
    created_dt = _parse_timestamp(created, "receipt.created_at")
    red_items: list[dict[str, Any]] = []
    commands: set[str] = set()
    for entry in selected:
        intended = entry.get("intended_red")
        if not isinstance(intended, Mapping):
            raise ValueError(
                f"requirement {entry.get('id')} has no intended RED mapping"
            )
        command = intended.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError(
                f"requirement {entry.get('id')} has no concrete RED command"
            )
        commands.add(command)
        red_items.append(
            {
                "requirement_id": entry.get("id"),
                "test": intended.get("test"),
                "command": command,
                "expected_missing_behavior": intended.get("expected_missing_behavior"),
                "statement_sha256": entry.get("statement_sha256"),
            }
        )
        assignment_time = _parse_timestamp(
            entry.get("owner_assigned_at"),
            f"requirement {entry.get('id')}.owner_assigned_at",
        )
        if assignment_time >= created_dt:
            raise ValueError(
                "owner assignment timestamp must precede the pre-RED receipt"
            )
    if not commands:
        raise ValueError("task has no concrete intended RED command")
    if commands != {red_command}:
        raise ValueError(
            "red_command must exactly match the task's frozen intended RED command"
        )
    red_items.sort(key=lambda item: item["requirement_id"])
    receipt = {
        "schema_version": "1.0",
        "task": task,
        "agent_id": agent,
        "registry_sha256": registry_sha256(assigned_registry),
        "normative_sha": assigned_registry.get("normative_sha"),
        "created_at": created,
        "red_command": red_command,
        "owner_assignments": assignments,
        "red_requirements": red_items,
    }
    if red_started_at is not None:
        red_started = _parse_timestamp(
            _timestamp(red_started_at), "receipt.red_started_at"
        )
        if red_started <= created_dt:
            raise ValueError("RED timestamp precedes the immutable pre-RED receipt")
        receipt["red_started_at"] = _timestamp(red_started)
    return receipt


def _write_document_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    """Create a receipt once; an existing path is never overwritten."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise ValueError(f"receipt already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def create_pre_red_receipt(
    assigned_registry: Mapping[str, Any],
    *,
    receipt_path: Path,
    task: int,
    red_command: str,
    created_at: datetime | None = None,
    red_started_at: datetime | None = None,
) -> dict[str, Any]:
    """Create and durably publish one immutable pre-RED receipt."""

    receipt = build_pre_red_receipt(
        assigned_registry,
        task=task,
        red_command=red_command,
        created_at=created_at,
        red_started_at=red_started_at,
    )
    _write_document_exclusive(receipt_path, receipt)
    return receipt


def verify_pre_red_receipt(
    assigned_registry: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    task: int,
    expected_red_command: str,
) -> None:
    """Verify that a receipt is an exact, non-reordered snapshot of ownership."""

    if not isinstance(receipt, Mapping):
        raise ValueError("pre-RED receipt must be an object")
    selected = _task_requirements(assigned_registry, task)
    frozen_red_command = _expected_task_command(assigned_registry, task)
    if expected_red_command != frozen_red_command:
        raise ValueError(
            "expected RED command does not match the registry's frozen command"
        )
    if receipt.get("schema_version") != "1.0":
        raise ValueError("pre-RED receipt schema_version must be '1.0'")
    if receipt.get("task") != task:
        raise ValueError("pre-RED receipt task does not match")
    if receipt.get("registry_sha256") != registry_sha256(assigned_registry):
        raise ValueError("pre-RED receipt registry hash does not match registry hash")
    if receipt.get("normative_sha") != assigned_registry.get("normative_sha"):
        raise ValueError("pre-RED receipt NORMATIVE_SHA does not match registry")
    red_command = receipt.get("red_command")
    if red_command != frozen_red_command:
        raise ValueError("pre-RED receipt RED command does not match registry")
    if (
        not isinstance(red_command, str)
        or not red_command.strip()
        or PLACEHOLDER.search(red_command)
    ):
        raise ValueError("pre-RED receipt RED command is not concrete")
    created_dt = _parse_timestamp(receipt.get("created_at"), "receipt.created_at")
    assignments = receipt.get("owner_assignments")
    if not isinstance(assignments, list):
        raise ValueError("pre-RED receipt owner_assignments must be a list")
    expected_assignments, expected_agent = _receipt_assignments(
        assigned_registry, selected
    )
    if assignments != expected_assignments:
        raise ValueError("pre-RED receipt owner assignments do not match registry")
    if receipt.get("agent_id") != expected_agent:
        raise ValueError("pre-RED receipt Agent ID does not match owner assignments")
    red_requirements = receipt.get("red_requirements")
    if not isinstance(red_requirements, list):
        raise ValueError("pre-RED receipt red_requirements must be a list")
    expected_red: list[dict[str, Any]] = []
    for entry in selected:
        intended = entry.get("intended_red")
        if not isinstance(intended, Mapping):
            raise ValueError("pre-RED receipt is missing an intended RED mapping")
        intended_command = intended.get("command")
        if not isinstance(intended_command, str) or not intended_command.strip():
            raise ValueError(
                "pre-RED receipt is missing a concrete intended RED command"
            )
        expected_red.append(
            {
                "requirement_id": entry.get("id"),
                "test": intended.get("test"),
                "command": intended_command,
                "expected_missing_behavior": intended.get("expected_missing_behavior"),
                "statement_sha256": entry.get("statement_sha256"),
            }
        )
        assignment_time = _parse_timestamp(
            entry.get("owner_assigned_at"),
            f"requirement {entry.get('id')}.owner_assigned_at",
        )
        if assignment_time >= created_dt:
            raise ValueError("owner assignment timestamp follows receipt creation")
    expected_red.sort(key=lambda item: item["requirement_id"])
    if red_requirements != expected_red:
        raise ValueError("pre-RED receipt requirement mappings do not match registry")
    red_started_at = receipt.get("red_started_at")
    if red_started_at is not None:
        if _parse_timestamp(red_started_at, "receipt.red_started_at") <= created_dt:
            raise ValueError("RED timestamp precedes the immutable pre-RED receipt")


def _repo_relative(path: Path, repo_root: Path) -> str:
    candidate = Path(os.path.abspath(path if path.is_absolute() else repo_root / path))
    try:
        relative = candidate.relative_to(Path(os.path.abspath(repo_root)))
    except ValueError as exc:
        raise ValueError(f"path is outside the Git repository: {path}") from exc
    return relative.as_posix()


def _write_index_tree(*, repo_root: Path) -> str:
    try:
        value = subprocess.run(
            ["git", "write-tree"],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_root,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("cannot freeze the Git index tree") from exc
    if not re.fullmatch(r"[0-9a-f]{40,64}", value):
        raise ValueError("git write-tree returned an invalid tree identity")
    return value


def _tree_path_changed(path: Path, *, repo_root: Path, tree_sha: str) -> bool:
    candidate = _repo_relative(path, repo_root)
    try:
        output = subprocess.run(
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "HEAD",
                tree_sha,
                "--",
                candidate,
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_root,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(output)


def _read_git_blob(
    path: Path,
    *,
    repo_root: Path,
    treeish: str,
) -> bytes:
    relative = _repo_relative(path, repo_root)
    try:
        result = subprocess.run(
            ["git", "show", f"{treeish}:{relative}"],
            check=True,
            capture_output=True,
            cwd=repo_root,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"Git blob is unavailable at {treeish}:{relative}") from exc
    return result.stdout


def _load_git_document(
    path: Path,
    *,
    repo_root: Path,
    treeish: str,
) -> dict[str, Any]:
    try:
        value = json.loads(
            _read_git_blob(
                path,
                repo_root=repo_root,
                treeish=treeish,
            ).decode("utf-8-sig")
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Git document is not valid JSON-compatible YAML: {treeish}:{path}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(f"Git document must contain an object: {treeish}:{path}")
    return value


def _require_git_commit(candidate_sha: Any, *, repo_root: Path) -> str:
    if not isinstance(candidate_sha, str) or not re.fullmatch(
        r"[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?", candidate_sha
    ):
        raise ValueError("NORMATIVE_SHA must be a complete Git commit SHA")
    try:
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", f"{candidate_sha}^{{commit}}"],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_root,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("NORMATIVE_SHA does not identify a repository commit") from exc
    return resolved.lower()


def _validate_staged_notes(
    registry: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    task: int,
    repo_root: Path,
    tree_sha: str,
) -> None:
    selected = _task_requirements(registry, task)
    grouped: dict[str, list[str]] = {}
    for entry in selected:
        note_path = entry.get("implementation_note_path")
        if not isinstance(note_path, str) or not note_path.strip():
            raise ValueError(
                f"requirement {entry.get('id')} has no implementation note"
            )
        grouped.setdefault(note_path, []).append(str(entry.get("id")))

    for note_path, requirement_ids in grouped.items():
        target = repo_root / note_path
        if not _tree_path_changed(target, repo_root=repo_root, tree_sha=tree_sha):
            raise ValueError(f"implementation note must be staged: {note_path}")
        try:
            content = _read_git_blob(
                target,
                repo_root=repo_root,
                treeish=tree_sha,
            ).decode("utf-8-sig")
        except UnicodeError as exc:
            raise ValueError(f"implementation note is not UTF-8: {note_path}") from exc
        if not content.strip():
            raise ValueError(f"implementation note is empty: {note_path}")
        for sentinel in NOTE_TEMPLATE_SENTINELS:
            if sentinel in content:
                raise ValueError(
                    f"implementation note contains an unreplaced template value: {note_path}"
                )
        match = NOTE_METADATA_BLOCK.search(content)
        if match is None:
            raise ValueError(
                f"implementation note lacks a JSON-compatible metadata block: {note_path}"
            )
        try:
            metadata = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"implementation note metadata is not valid JSON: {note_path}"
            ) from exc
        _validate_note_metadata(
            metadata,
            registry=registry,
            receipt=receipt,
            selected=[
                entry
                for entry in selected
                if entry.get("implementation_note_path") == note_path
            ],
            requirement_ids=requirement_ids,
            repo_root=repo_root,
            note_path=note_path,
        )


def _require_log_sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError(f"{name} must be a SHA-256 value")
    return value.lower()


def _validate_note_metadata(
    metadata: Any,
    *,
    registry: Mapping[str, Any],
    receipt: Mapping[str, Any],
    selected: list[dict[str, Any]],
    requirement_ids: list[str],
    repo_root: Path,
    note_path: str,
) -> None:
    if not isinstance(metadata, Mapping):
        raise ValueError(f"implementation note metadata must be an object: {note_path}")
    expected_fields = {
        "schema_version",
        "slice_id",
        "phase",
        "owner_role",
        "owner_agent_id",
        "normative_sha",
        "base_sha",
        "candidate_sha",
        "requirement_ids",
        "status",
        "red",
        "green",
        "real_evidence_limitations",
    }
    if set(metadata) != expected_fields:
        raise ValueError(
            f"implementation note metadata fields are incomplete or unknown: {note_path}"
        )
    if metadata.get("schema_version") != "1.0":
        raise ValueError(
            f"implementation note schema_version must be '1.0': {note_path}"
        )
    for field in ("slice_id", "phase", "real_evidence_limitations"):
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip() or PLACEHOLDER.search(value):
            raise ValueError(
                f"implementation note {field} is not concrete: {note_path}"
            )
    roles = {str(entry.get("accountable_role")) for entry in selected}
    owners = {str(entry.get("owner_agent_id")) for entry in selected}
    if len(roles) != 1 or metadata.get("owner_role") != next(iter(roles)):
        raise ValueError(
            f"implementation note owner_role does not match registry: {note_path}"
        )
    if len(owners) != 1 or metadata.get("owner_agent_id") != next(iter(owners)):
        raise ValueError(
            f"implementation note owner_agent_id does not match registry: {note_path}"
        )
    if metadata.get("normative_sha") != registry.get("normative_sha"):
        raise ValueError(
            f"implementation note NORMATIVE_SHA does not match: {note_path}"
        )
    head_sha = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    ).stdout.strip()
    if metadata.get("base_sha") != head_sha:
        raise ValueError(
            f"implementation note base_sha must equal candidate base HEAD: {note_path}"
        )
    if metadata.get("candidate_sha") is not None:
        raise ValueError(
            f"candidate draft must leave candidate_sha null until attestation: {note_path}"
        )
    note_requirement_ids = metadata.get("requirement_ids")
    if (
        not isinstance(note_requirement_ids, list)
        or set(note_requirement_ids) != set(requirement_ids)
        or len(note_requirement_ids) != len(requirement_ids)
    ):
        raise ValueError(
            f"implementation note requirement_ids do not exactly match registry: {note_path}"
        )
    if metadata.get("status") != "in_progress":
        raise ValueError(
            f"candidate implementation note status must be in_progress: {note_path}"
        )

    red = metadata.get("red")
    green = metadata.get("green")
    if not isinstance(red, Mapping) or not isinstance(green, Mapping):
        raise ValueError(
            f"implementation note RED/GREEN evidence must be objects: {note_path}"
        )
    frozen_red = _expected_task_command(registry, int(receipt.get("task", 0)))
    if red.get("command") != frozen_red:
        raise ValueError(
            f"implementation note RED command does not match registry: {note_path}"
        )
    red_exit = red.get("exit_code")
    if not isinstance(red_exit, int) or isinstance(red_exit, bool) or red_exit == 0:
        raise ValueError(
            f"implementation note RED exit_code must be non-zero: {note_path}"
        )
    _require_log_sha(red.get("log_sha256"), f"{note_path}.red.log_sha256")
    failure = red.get("failure_classification")
    if (
        not isinstance(failure, str)
        or not failure.strip()
        or PLACEHOLDER.search(failure)
    ):
        raise ValueError(
            f"implementation note RED failure is not concrete: {note_path}"
        )
    red_started = _parse_timestamp(red.get("started_at"), f"{note_path}.red.started_at")
    receipt_created = _parse_timestamp(
        receipt.get("created_at"), f"{note_path}.receipt.created_at"
    )
    if red_started <= receipt_created:
        raise ValueError(
            f"implementation note RED started before its receipt: {note_path}"
        )

    green_commands = {
        entry.get("intended_green", {}).get("command")
        for entry in selected
        if isinstance(entry.get("intended_green"), Mapping)
    }
    if len(green_commands) != 1 or green.get("command") != next(
        iter(green_commands), None
    ):
        raise ValueError(
            f"implementation note GREEN command does not match registry: {note_path}"
        )
    if green.get("exit_code") != 0:
        raise ValueError(
            f"implementation note GREEN exit_code must be zero: {note_path}"
        )
    test_count = green.get("test_count")
    if (
        not isinstance(test_count, int)
        or isinstance(test_count, bool)
        or test_count < 1
    ):
        raise ValueError(
            f"implementation note GREEN test_count must be positive: {note_path}"
        )
    _require_log_sha(green.get("log_sha256"), f"{note_path}.green.log_sha256")


def verify_candidate_index(
    *,
    registry_path: Path,
    manifest_path: Path,
    receipt_path: Path,
    task: int,
    expected_red_command: str | None,
    repo_root: Path,
) -> None:
    """Verify the candidate from Git index blobs, never the mutable worktree."""

    tree_sha = _write_index_tree(repo_root=repo_root)
    for path, label in (
        (registry_path, "registry"),
        (receipt_path, "pre-RED receipt"),
    ):
        if not _tree_path_changed(path, repo_root=repo_root, tree_sha=tree_sha):
            raise ValueError(f"candidate {label} must be staged")

    index_manifest = _read_git_blob(
        manifest_path,
        repo_root=repo_root,
        treeish=tree_sha,
    )
    try:
        head_manifest = _read_git_blob(
            manifest_path,
            repo_root=repo_root,
            treeish="HEAD",
        )
    except ValueError as exc:
        raise ValueError(
            "candidate verification requires an immutable HEAD manifest"
        ) from exc
    if index_manifest != head_manifest:
        raise ValueError(
            "candidate must not modify normative-baseline.json; create a new "
            "governance transition instead"
        )
    manifest = _load_git_document(
        manifest_path,
        repo_root=repo_root,
        treeish="HEAD",
    )
    normative_sha = _require_git_commit(
        manifest.get("normative_sha"),
        repo_root=repo_root,
    )
    registry = _load_git_document(
        registry_path,
        repo_root=repo_root,
        treeish=tree_sha,
    )

    def staged_source_loader(source_path: str) -> bytes:
        return _read_git_blob(
            repo_root / source_path,
            repo_root=repo_root,
            treeish=normative_sha,
        )

    validate_registry(
        registry,
        manifest,
        root=repo_root,
        source_loader=staged_source_loader,
    )
    receipt = _load_git_document(
        receipt_path,
        repo_root=repo_root,
        treeish=tree_sha,
    )
    verify_pre_red_receipt(
        registry,
        receipt,
        task=task,
        expected_red_command=expected_red_command
        or _expected_task_command(registry, task),
    )
    _validate_staged_notes(
        registry,
        receipt,
        task=task,
        repo_root=repo_root,
        tree_sha=tree_sha,
    )
    if _write_index_tree(repo_root=repo_root) != tree_sha:
        raise ValueError("Git index changed during candidate verification")


def _expected_task_command(registry: Mapping[str, Any], task: int) -> str:
    selected = _task_requirements(registry, task)
    commands = {
        item.get("intended_red", {}).get("command")
        for item in selected
        if isinstance(item.get("intended_red"), Mapping)
    }
    if len(commands) != 1 or not next(iter(commands), None):
        raise ValueError("task must have one complete intended RED command")
    return next(iter(commands))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--phase",
        choices=("bootstrap", "pre-red", "candidate", "governance-transition"),
    )
    parser.add_argument("--assign-owner", action="store_true")
    parser.add_argument("--reset-owner", action="store_true")
    parser.add_argument("--task", type=int)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--agent-id")
    parser.add_argument("--assigned-at")
    parser.add_argument("--created-at")
    parser.add_argument("--red-started-at")
    parser.add_argument("--red-command")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-agent-id")
    parser.add_argument("--require-normative-sha")
    parser.add_argument("--check-index", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path.cwd().resolve()
    if args.phase == "candidate" and args.check_index:
        if args.task is None:
            raise ValueError("--task is required for candidate verification")
        if not args.receipt:
            raise ValueError("--receipt is required for candidate verification")
        verify_candidate_index(
            registry_path=args.registry,
            manifest_path=args.manifest,
            receipt_path=args.receipt,
            task=args.task,
            expected_red_command=args.red_command,
            repo_root=repo_root,
        )
        return 0

    registry = load_document(args.registry)
    manifest = load_document(args.manifest)
    validate_registry(registry, manifest, root=repo_root)
    if args.assign_owner or args.reset_owner:
        if args.assign_owner and args.reset_owner:
            raise ValueError("--assign-owner and --reset-owner are mutually exclusive")
        if args.task is None or not args.output:
            raise ValueError("owner mutation requires --task and --output")
        if args.assign_owner:
            if not args.agent_id:
                raise ValueError("--assign-owner requires --agent-id")
            updated = assign_owner(
                registry,
                task=args.task,
                agent_id=args.agent_id,
                assigned_at=(
                    _parse_timestamp(args.assigned_at, "--assigned-at")
                    if args.assigned_at
                    else None
                ),
            )
        else:
            if not args.expected_agent_id:
                raise ValueError("--reset-owner requires --expected-agent-id")
            updated = reset_owner(
                registry,
                task=args.task,
                expected_agent_id=args.expected_agent_id,
            )
        write_document(args.output, updated)
        return 0
    if args.phase is None:
        raise ValueError("--phase or an owner mutation command is required")
    if args.phase == "bootstrap":
        if any(
            item.get("owner_agent_id") is not None for item in registry["requirements"]
        ):
            raise ValueError(
                "bootstrap registry must not contain a concrete owner assignment"
            )
        return 0
    if args.phase == "governance-transition":
        if not args.require_normative_sha:
            raise ValueError("governance transition requires --require-normative-sha")
        if registry.get("normative_sha") != args.require_normative_sha:
            raise ValueError(
                "registry normative_sha does not match required transition SHA"
            )
        try:
            from tools.v2.transition_normative_baseline import validate_review_chain
        except ModuleNotFoundError:
            from transition_normative_baseline import validate_review_chain  # type: ignore[no-redef]

        validate_review_chain(
            manifest.get("review_chain"),
            candidate_sha=str(manifest.get("normative_sha")),
        )
        return 0
    if args.task is None:
        raise ValueError("--task is required for this phase")
    if args.phase == "pre-red" and args.agent_id:
        assigned = assign_owner(
            registry,
            task=args.task,
            agent_id=args.agent_id,
            assigned_at=(
                _parse_timestamp(args.assigned_at, "--assigned-at")
                if args.assigned_at
                else None
            ),
        )
        if not args.output:
            raise ValueError("--output is required when assigning an owner")
        write_document(args.output, assigned)
        return 0
    if args.phase not in {"pre-red", "candidate"}:
        raise ValueError(f"unsupported phase {args.phase}")
    if not args.receipt:
        raise ValueError("--receipt is required for receipt verification")
    if args.phase == "pre-red":
        expected_command = args.red_command or _expected_task_command(
            registry, args.task
        )
        if args.receipt.exists():
            receipt = load_document(args.receipt)
            verify_pre_red_receipt(
                registry,
                receipt,
                task=args.task,
                expected_red_command=expected_command,
            )
            return 0
        if args.created_at or args.red_started_at:
            raise ValueError(
                "pre-RED receipt timestamps are verifier-owned and cannot be supplied"
            )
        create_pre_red_receipt(
            registry,
            receipt_path=args.receipt,
            task=args.task,
            red_command=expected_command,
        )
        return 0
    receipt = load_document(args.receipt)
    expected_command = args.red_command or _expected_task_command(registry, args.task)
    verify_pre_red_receipt(
        registry,
        receipt,
        task=args.task,
        expected_red_command=expected_command,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
