#!/usr/bin/env python3
"""Create a reviewed proposed-gate normative-baseline transition."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Sequence

try:
    from tools.v2.build_requirement_registry import (
        ALLOWED_CLASSIFICATIONS,
        load_document,
        write_document,
    )
except ModuleNotFoundError:  # Direct execution from tools/v2.
    from build_requirement_registry import (  # type: ignore[no-redef]
        ALLOWED_CLASSIFICATIONS,
        load_document,
        write_document,
    )


REVIEW_ROLES = (
    "specification_authority",
    "plan_executability",
    "official_framework",
)
HEX_SHA = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
PLACEHOLDER = re.compile(
    r"(?:\btbd\b|\btodo\b|placeholder|unknown|unassigned|shared[-_ ]owner|"
    r"catch[-_ ]all|dummy|fake|example[-_ ]only)",
    re.IGNORECASE,
)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be an ISO-8601 timestamp")
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _require_candidate_sha(value: Any) -> str:
    if not isinstance(value, str) or not HEX_SHA.fullmatch(value):
        raise ValueError("candidate_sha must be a 40- or 64-character hexadecimal SHA")
    return value.lower()


def _require_repository_commit(value: Any, *, repo_root: Path) -> str:
    candidate = _require_candidate_sha(value)
    try:
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", f"{candidate}^{{commit}}"],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_root,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("candidate_sha does not identify a repository commit") from exc
    return resolved.lower()


def _candidate_blob_sha256(
    *,
    repo_root: Path,
    candidate_sha: str,
    source_path: str,
) -> str:
    path = Path(source_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"manifest source path escapes repository: {source_path}")
    try:
        blob = subprocess.run(
            ["git", "show", f"{candidate_sha}:{path.as_posix()}"],
            check=True,
            capture_output=True,
            cwd=repo_root,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(
            f"candidate commit does not contain manifest source {source_path}"
        ) from exc
    return sha256(blob).hexdigest()


def _require_reviewer(value: Any, role: str) -> str:
    if not isinstance(value, str) or not value.strip() or PLACEHOLDER.search(value):
        raise ValueError(f"ordered review chain has no concrete reviewer for {role}")
    return value.strip()


def validate_review_chain(
    review_chain: Sequence[Mapping[str, Any]] | Any,
    *,
    candidate_sha: str | None = None,
    evidence_sha256: str | None = None,
    evidence_path: str | None = None,
) -> list[dict[str, Any]]:
    """Validate all three sequential Task 0 review authorities."""

    if not isinstance(review_chain, list) or len(review_chain) != len(REVIEW_ROLES):
        raise ValueError("ordered review chain must contain all three required reviews")
    expected_sha = _require_candidate_sha(candidate_sha) if candidate_sha else None
    normalized: list[dict[str, Any]] = []
    previous_time: datetime | None = None
    reviewers: set[str] = set()
    for index, expected_role in enumerate(REVIEW_ROLES, start=1):
        raw_review = review_chain[index - 1]
        if not isinstance(raw_review, Mapping):
            raise ValueError("ordered review chain entries must be objects")
        review = deepcopy(dict(raw_review))
        if review.get("role") != expected_role or review.get("sequence") != index:
            raise ValueError(
                "ordered review chain must be specification_authority, "
                "plan_executability, official_framework with sequences 1, 2, 3"
            )
        reviewer = _require_reviewer(review.get("reviewer"), expected_role)
        if reviewer in reviewers:
            raise ValueError(
                "ordered review chain requires three independent reviewers"
            )
        reviewers.add(reviewer)
        if review.get("result") != "approved":
            raise ValueError(
                f"ordered review chain review {expected_role} is not approved"
            )
        for finding_name in ("critical_findings", "important_findings"):
            count = review.get(finding_name)
            if not isinstance(count, int) or isinstance(count, bool) or count != 0:
                raise ValueError(
                    f"ordered review chain review {expected_role} has unresolved findings"
                )
        reviewed_at = _parse_timestamp(
            review.get("reviewed_at"), f"review {expected_role}.reviewed_at"
        )
        if previous_time is not None and reviewed_at <= previous_time:
            raise ValueError("ordered review chain timestamps must increase strictly")
        previous_time = reviewed_at
        review_sha = review.get("candidate_sha")
        if review_sha is None:
            raise ValueError(
                f"ordered review chain review {expected_role} is missing candidate SHA"
            )
        normalized_sha = _require_candidate_sha(review_sha)
        if expected_sha is not None and normalized_sha != expected_sha:
            raise ValueError(
                f"ordered review chain review {expected_role} targets another candidate"
            )
        review["candidate_sha"] = normalized_sha
        review_evidence_sha = review.get("evidence_sha256")
        if not isinstance(review_evidence_sha, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", review_evidence_sha
        ):
            raise ValueError(
                f"ordered review chain review {expected_role} lacks evidence SHA-256"
            )
        normalized_evidence_sha = review_evidence_sha.lower()
        if (
            evidence_sha256 is not None
            and normalized_evidence_sha != evidence_sha256.lower()
        ):
            raise ValueError(
                f"ordered review chain review {expected_role} targets another evidence note"
            )
        review_evidence_path = _require_reviewer(
            review.get("evidence_path"), f"{expected_role} evidence"
        )
        if evidence_path is not None and review_evidence_path != evidence_path:
            raise ValueError(
                f"ordered review chain review {expected_role} has another evidence path"
            )
        _require_reviewer(review.get("scope"), f"{expected_role} review scope")
        _require_reviewer(review.get("command"), f"{expected_role} review command")
        review["evidence_sha256"] = normalized_evidence_sha
        normalized.append(review)
    return normalized


def transition_manifest(
    current_manifest: Mapping[str, Any],
    *,
    promote_path: str,
    candidate_sha: str,
    review_chain: Sequence[Mapping[str, Any]],
    repo_root: Path,
    review_evidence_sha256: str,
    review_evidence_path: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Promote exactly one ``proposed_gate`` after the complete review chain."""

    if not isinstance(current_manifest, Mapping):
        raise ValueError("current manifest must be an object")
    if current_manifest.get("schema_version") != "1.0":
        raise ValueError("current manifest schema_version must be '1.0'")
    repository = repo_root.resolve()
    current_sha = _require_repository_commit(
        current_manifest.get("normative_sha"), repo_root=repository
    )
    reviewed_sha = _require_repository_commit(candidate_sha, repo_root=repository)
    if reviewed_sha == current_sha:
        raise ValueError("candidate_sha must create a new normative baseline")
    reviews = validate_review_chain(
        review_chain,
        candidate_sha=reviewed_sha,
        evidence_sha256=review_evidence_sha256,
        evidence_path=review_evidence_path,
    )
    if not isinstance(promote_path, str) or not promote_path.strip():
        raise ValueError("promote_path must be a non-empty relative path")
    path = Path(promote_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("promote_path must stay inside the repository")
    generation = current_manifest.get("generation")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
    ):
        raise ValueError("current manifest generation must be a positive integer")
    files = current_manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("current manifest files must be a non-empty list")
    for index, item in enumerate(files):
        if not isinstance(item, Mapping):
            raise ValueError(f"current manifest files[{index}] must be an object")
        if item.get("classification") not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(
                f"current manifest files[{index}] has an invalid classification"
            )
        _require_candidate_sha(item.get("sha256"))
        source_path = item.get("path")
        if not isinstance(source_path, str) or not source_path.strip():
            raise ValueError(f"current manifest files[{index}] has no source path")

    matches = [
        item
        for item in files
        if isinstance(item, Mapping) and item.get("path") == promote_path
    ]
    if len(matches) != 1:
        raise ValueError("promoted source must exist exactly once in the manifest")
    if matches[0].get("classification") != "proposed_gate":
        raise ValueError("only a proposed_gate source can be promoted")
    paths = [item.get("path") for item in files if isinstance(item, Mapping)]
    if len(paths) != len(set(paths)):
        raise ValueError("current manifest contains duplicate source paths")
    generated_value = generated_at or datetime.now(UTC)
    if generated_value.tzinfo is None or generated_value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    generated_dt = generated_value.astimezone(UTC)
    final_review_dt = _parse_timestamp(
        reviews[-1]["reviewed_at"], "final review timestamp"
    )
    if generated_dt <= final_review_dt:
        raise ValueError("generated_at must follow the final ordered review")

    next_manifest = deepcopy(dict(current_manifest))
    next_manifest["generation"] = generation + 1
    next_manifest["normative_sha"] = reviewed_sha
    next_manifest["generated_at"] = _iso_utc(generated_value)
    next_manifest["review_chain"] = reviews
    next_manifest["previous_normative_sha"] = current_manifest.get("normative_sha")
    next_manifest["transition"] = {
        "type": "proposed_gate_promotion",
        "promoted_path": promote_path,
        "candidate_sha": reviewed_sha,
    }
    for raw_file in next_manifest["files"]:
        raw_file["sha256"] = _candidate_blob_sha256(
            repo_root=repository,
            candidate_sha=reviewed_sha,
            source_path=str(raw_file["path"]),
        )
        if raw_file.get("path") != promote_path:
            continue
        raw_file["classification"] = "approved_normative"
        raw_file["authority_class"] = "approved_normative"
        raw_file.pop("normative_regions", None)
    for raw_file in next_manifest["files"]:
        classification = raw_file.get("classification")
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(
                f"transition produced invalid classification {classification!r}"
            )
    return next_manifest


def _load_review_chain(
    path: Path | None, current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if path is not None:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(value, Mapping):
            value = value.get("review_chain")
        if not isinstance(value, list):
            raise ValueError("review-chain document must contain an array")
        return value
    value = current.get("review_chain")
    if not isinstance(value, list):
        raise ValueError("a complete --review-chain JSON document is required")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-manifest", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--promote", required=True)
    parser.add_argument("--review-chain", type=Path)
    parser.add_argument("--review-note", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    current = load_document(args.current_manifest)
    if args.review_note is None or not args.review_note.is_file():
        raise ValueError("a concrete --review-note file is required")
    note_bytes = args.review_note.read_bytes()
    try:
        note = note_bytes.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("review note must be UTF-8 text") from exc
    if not note.strip() or PLACEHOLDER.search(note):
        raise ValueError("review note is empty or contains placeholder review evidence")
    try:
        review_note_path = args.review_note.resolve().relative_to(Path.cwd().resolve())
    except ValueError as exc:
        raise ValueError("review note must stay inside the repository") from exc
    review_note_sha256 = sha256(note_bytes).hexdigest()
    reviews = _load_review_chain(args.review_chain, current)
    transitioned = transition_manifest(
        current,
        promote_path=args.promote,
        candidate_sha=args.candidate_sha,
        review_chain=reviews,
        repo_root=Path.cwd(),
        review_evidence_sha256=review_note_sha256,
        review_evidence_path=review_note_path.as_posix(),
    )
    write_document(args.output, transitioned)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
