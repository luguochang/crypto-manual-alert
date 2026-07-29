#!/usr/bin/env python3
"""Build the immutable generation-one normative baseline after ordered reviews."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Mapping, Sequence

try:
    from tools.v2.build_requirement_registry import (
        ALLOWED_CLASSIFICATIONS,
        write_document,
    )
    from tools.v2.transition_normative_baseline import (
        PLACEHOLDER,
        _iso_utc,
        _parse_timestamp,
        _require_repository_commit,
        validate_review_chain,
    )
except ModuleNotFoundError:  # Direct execution from tools/v2.
    from build_requirement_registry import (  # type: ignore[no-redef]
        ALLOWED_CLASSIFICATIONS,
        write_document,
    )
    from transition_normative_baseline import (  # type: ignore[no-redef]
        PLACEHOLDER,
        _iso_utc,
        _parse_timestamp,
        _require_repository_commit,
        validate_review_chain,
    )


AUTHORITY_FIELD = re.compile(
    r"^>\s*authority_class:\s*([a-z_]+)\s*$", re.MULTILINE
)
REGIONS_FIELD = re.compile(
    r"^>\s*normative_regions:\s*([^\r\n]+?)\s*$", re.MULTILINE
)
HEX_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _relative_path(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty repository-relative path")
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or normalized.startswith("/"):
        raise ValueError(f"{name} must stay inside the repository")
    return path.as_posix()


def _candidate_blob(
    *, repo_root: Path, candidate_sha: str, source_path: str
) -> bytes:
    path = _relative_path(source_path, "candidate source path")
    try:
        return subprocess.run(
            ["git", "show", f"{candidate_sha}:{path}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(
            f"candidate commit does not contain required source {path}"
        ) from exc


def _candidate_json(
    *, repo_root: Path, candidate_sha: str, source_path: str
) -> tuple[dict[str, Any], bytes]:
    payload = _candidate_blob(
        repo_root=repo_root,
        candidate_sha=candidate_sha,
        source_path=source_path,
    )
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("normative source policy must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("normative source policy must be an object")
    return value, payload


def _policy_regions(value: Any, source_path: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError(
            f"mixed source {source_path} must define normative_regions"
        )
    regions: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw_region in enumerate(value):
        raw_anchor = (
            raw_region.get("anchor") if isinstance(raw_region, Mapping) else raw_region
        )
        if not isinstance(raw_anchor, str) or not raw_anchor.strip():
            raise ValueError(
                f"{source_path}.normative_regions[{index}] has no anchor"
            )
        anchor = raw_anchor.strip()
        if anchor in seen:
            raise ValueError(
                f"{source_path}.normative_regions contains duplicate {anchor!r}"
            )
        seen.add(anchor)
        regions.append({"anchor": anchor})
    return regions


def _document_declarations(
    *, source_path: str, payload: bytes
) -> tuple[str, list[str]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError(f"normative source must be UTF-8: {source_path}") from exc
    authority = AUTHORITY_FIELD.findall(text)
    if len(authority) != 1:
        raise ValueError(
            f"source {source_path} must declare exactly one authority_class"
        )
    regions = REGIONS_FIELD.findall(text)
    if len(regions) > 1:
        raise ValueError(
            f"source {source_path} must declare normative_regions at most once"
        )
    declared = (
        [anchor.strip() for anchor in regions[0].split(",") if anchor.strip()]
        if regions
        else []
    )
    if len(declared) != len(set(declared)):
        raise ValueError(f"source {source_path} has duplicate normative_regions")
    for anchor in declared:
        start = f"<!-- normative:start {anchor} -->"
        end = f"<!-- normative:end {anchor} -->"
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError(
                f"source {source_path} normative_regions anchor {anchor!r} "
                "must have one start and end marker"
            )
        if text.index(start) >= text.index(end):
            raise ValueError(
                f"source {source_path} normative_regions anchor {anchor!r} is reversed"
            )
    return authority[0], declared


def _manifest_files(
    *, policy: Mapping[str, Any], repo_root: Path, candidate_sha: str
) -> list[dict[str, Any]]:
    if policy.get("schema_version") != "1.0":
        raise ValueError("normative source policy schema_version must be '1.0'")
    sources = policy.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("normative source policy must contain sources")

    entries: list[dict[str, Any]] = []
    paths: set[str] = set()
    for index, raw_source in enumerate(sources):
        if not isinstance(raw_source, Mapping):
            raise ValueError(f"source policy sources[{index}] must be an object")
        source_path = _relative_path(
            raw_source.get("path"), f"source policy sources[{index}].path"
        )
        if source_path in paths:
            raise ValueError(f"source policy contains duplicate path {source_path}")
        paths.add(source_path)
        classification = raw_source.get("classification")
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(
                f"source policy {source_path} has invalid classification"
            )
        precedence = raw_source.get("precedence")
        if (
            not isinstance(precedence, int)
            or isinstance(precedence, bool)
            or precedence < 1
        ):
            raise ValueError(
                f"source policy {source_path} must have positive precedence"
            )
        payload = _candidate_blob(
            repo_root=repo_root,
            candidate_sha=candidate_sha,
            source_path=source_path,
        )
        declared_class, declared_regions = _document_declarations(
            source_path=source_path, payload=payload
        )
        if declared_class != classification:
            raise ValueError(
                f"source {source_path} authority_class {declared_class!r} "
                f"does not match policy {classification!r}"
            )

        entry: dict[str, Any] = {
            "path": source_path,
            "classification": classification,
            "precedence": precedence,
            "sha256": sha256(payload).hexdigest(),
        }
        if classification == "mixed":
            policy_regions = _policy_regions(
                raw_source.get("normative_regions"), source_path
            )
            policy_anchors = [item["anchor"] for item in policy_regions]
            if declared_regions != policy_anchors:
                raise ValueError(
                    f"source {source_path} normative_regions do not match policy"
                )
            entry["normative_regions"] = policy_regions
        elif raw_source.get("normative_regions") is not None or declared_regions:
            raise ValueError(
                f"non-mixed source {source_path} cannot declare normative_regions"
            )

        superseded_by = raw_source.get("superseded_by")
        if classification == "superseded":
            entry["superseded_by"] = _relative_path(
                superseded_by, f"source policy {source_path}.superseded_by"
            )
        elif superseded_by is not None:
            raise ValueError(
                f"non-superseded source {source_path} cannot define superseded_by"
            )
        entries.append(entry)

    for entry in entries:
        target = entry.get("superseded_by")
        if target is not None and target not in paths:
            raise ValueError(
                f"source {entry['path']} superseded_by target is not in policy"
            )
    return sorted(entries, key=lambda item: str(item["path"]))


def build_initial_manifest(
    *,
    candidate_sha: str,
    source_policy_path: str,
    review_chain: Sequence[Mapping[str, Any]],
    repo_root: Path,
    review_evidence_sha256: str,
    review_evidence_path: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build generation one from immutable candidate blobs after all reviews."""

    source_snapshot = inspect_candidate_sources(
        candidate_sha=candidate_sha,
        source_policy_path=source_policy_path,
        repo_root=repo_root,
    )
    reviewed_sha = str(source_snapshot["candidate_sha"])
    if not isinstance(review_evidence_sha256, str) or not HEX_SHA256.fullmatch(
        review_evidence_sha256
    ):
        raise ValueError("review_evidence_sha256 must be a SHA-256")
    reviews = validate_review_chain(
        review_chain,
        candidate_sha=reviewed_sha,
        evidence_sha256=review_evidence_sha256,
        evidence_path=review_evidence_path,
    )
    generated_value = generated_at or datetime.now(UTC)
    final_review = _parse_timestamp(
        reviews[-1]["reviewed_at"], "final review timestamp"
    )
    if generated_value.tzinfo is None or generated_value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    if generated_value.astimezone(UTC) <= final_review:
        raise ValueError("generated_at must follow the final ordered review")

    return {
        "schema_version": "1.0",
        "generation": 1,
        "normative_sha": reviewed_sha,
        "generated_at": _iso_utc(generated_value),
        "source_policy": deepcopy(source_snapshot["source_policy"]),
        "files": deepcopy(source_snapshot["files"]),
        "review_chain": reviews,
        "review_evidence": {
            "path": _relative_path(
                review_evidence_path, "review_evidence_path"
            ),
            "sha256": review_evidence_sha256.lower(),
        },
    }


def inspect_candidate_sources(
    *, candidate_sha: str, source_policy_path: str, repo_root: Path
) -> dict[str, Any]:
    """Validate and summarize a proposed source set before reviews begin."""

    repository = repo_root.resolve()
    reviewed_sha = _require_repository_commit(candidate_sha, repo_root=repository)
    policy_path = _relative_path(source_policy_path, "source_policy_path")
    policy, policy_payload = _candidate_json(
        repo_root=repository,
        candidate_sha=reviewed_sha,
        source_path=policy_path,
    )
    return {
        "candidate_sha": reviewed_sha,
        "source_policy": {
            "path": policy_path,
            "sha256": sha256(policy_payload).hexdigest(),
        },
        "files": _manifest_files(
            policy=policy, repo_root=repository, candidate_sha=reviewed_sha
        ),
    }


def _load_review_chain(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(value, Mapping):
        value = value.get("review_chain")
    if not isinstance(value, list):
        raise ValueError("review-chain document must contain an array")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--source-policy", required=True)
    parser.add_argument("--check-sources", action="store_true")
    parser.add_argument("--review-chain", type=Path)
    parser.add_argument("--review-note", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.check_sources:
        if any((args.review_chain, args.review_note, args.output)):
            raise ValueError(
                "--check-sources cannot be combined with review or output arguments"
            )
        snapshot = inspect_candidate_sources(
            candidate_sha=args.candidate_sha,
            source_policy_path=args.source_policy,
            repo_root=Path.cwd(),
        )
        print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
        return 0
    if args.review_chain is None or args.review_note is None or args.output is None:
        raise ValueError(
            "baseline generation requires --review-chain, --review-note and --output"
        )
    if args.output.exists():
        raise ValueError(f"initial normative baseline already exists: {args.output}")
    if not args.review_note.is_file():
        raise ValueError("a concrete --review-note file is required")
    note_bytes = args.review_note.read_bytes()
    try:
        note = note_bytes.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("review note must be UTF-8 text") from exc
    if not note.strip() or PLACEHOLDER.search(note):
        raise ValueError("review note is empty or contains placeholder review evidence")
    try:
        note_path = args.review_note.resolve().relative_to(Path.cwd().resolve())
    except ValueError as exc:
        raise ValueError("review note must stay inside the repository") from exc
    manifest = build_initial_manifest(
        candidate_sha=args.candidate_sha,
        source_policy_path=args.source_policy,
        review_chain=_load_review_chain(args.review_chain),
        repo_root=Path.cwd(),
        review_evidence_sha256=sha256(note_bytes).hexdigest(),
        review_evidence_path=note_path.as_posix(),
    )
    write_document(args.output, manifest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
