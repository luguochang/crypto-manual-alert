#!/usr/bin/env python3
"""Build and validate the V2 requirement registry.

Task 0B deliberately uses JSON-compatible YAML.  JSON is a YAML 1.2 subset,
so the bootstrap path can use only Python's standard library and still produce
files that are readable by normal YAML tooling after the dependency graph is
available.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Callable, Iterable, Mapping


SCHEMA_VERSION = "1.0"
ALLOWED_CLASSIFICATIONS = {
    "approved_normative",
    "mixed",
    "verified_evidence_index",
    "informative",
    "superseded",
    "proposed_gate",
}
EXCLUDED_CLASSIFICATIONS = {
    "verified_evidence_index",
    "informative",
    "superseded",
}
NORMATIVE_WORD = re.compile(r"\b(?:MUST|SHALL|REQUIRED|SHOULD)\b")
NORMATIVE_START = re.compile(
    r"^\s*<!--\s*normative:start\s+([A-Za-z0-9][A-Za-z0-9_.:-]*)\s*-->\s*$"
)
NORMATIVE_END = re.compile(
    r"^\s*<!--\s*normative:end\s+([A-Za-z0-9][A-Za-z0-9_.:-]*)\s*-->\s*$"
)
REQUIREMENT_MARKER = re.compile(
    r"^\s*<!--\s*requirement:\s*([A-Za-z0-9][A-Za-z0-9_.:-]*)\s*-->\s*$"
)
HEX_SHA = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
PLACEHOLDER_WORDS = (
    "tbd",
    "todo",
    "placeholder",
    "changeme",
    "change-me",
    "unknown",
    "unassigned",
    "shared-owner",
    "shared_owner",
    "catch-all",
    "catch_all",
    "dummy",
    "fake",
    "example-only",
    "local-only",
)
SourceLoader = Callable[[str], bytes]


def load_document(path: str | Path) -> dict[str, Any]:
    """Load a JSON-compatible YAML document using only ``json``."""

    target = Path(path)
    try:
        value = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"cannot load JSON-compatible YAML document {target}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(f"document {target} must contain a JSON object")
    return value


def write_document(path: str | Path, value: Mapping[str, Any]) -> None:
    """Write deterministic JSON, which is valid JSON-compatible YAML."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _as_root(root: str | Path | None) -> Path:
    return Path(root or ".").resolve()


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX_SHA.fullmatch(value))


def _require_sha(value: Any, name: str) -> str:
    if not _is_sha(value):
        raise ValueError(f"{name} must be a 40- or 64-character hexadecimal SHA")
    return str(value).lower()


def _safe_source_path(root: Path, source_path: str) -> Path:
    path = Path(source_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"source path escapes repository root: {source_path}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"source path escapes repository root: {source_path}") from exc
    if not resolved.is_file():
        raise ValueError(f"source file does not exist: {source_path}")
    return resolved


def _source_bytes(
    root: Path,
    source_path: str,
    source_loader: SourceLoader | None,
) -> bytes:
    if source_loader is not None:
        try:
            value = source_loader(source_path)
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot read source blob {source_path}: {exc}") from exc
        if not isinstance(value, bytes):
            raise ValueError(f"source loader returned non-bytes for {source_path}")
        return value
    return _safe_source_path(root, source_path).read_bytes()


def _manifest_files(
    manifest: Mapping[str, Any],
    root: Path,
    *,
    source_loader: SourceLoader | None = None,
) -> list[Mapping[str, Any]]:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"manifest schema_version must be {SCHEMA_VERSION!r}")
    generation = manifest.get("generation")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
    ):
        raise ValueError("manifest generation must be a positive integer")
    _require_sha(manifest.get("normative_sha"), "manifest normative_sha")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest files must be a non-empty list")

    seen: set[str] = set()
    result: list[Mapping[str, Any]] = []
    for index, raw_file in enumerate(files):
        item = _require_mapping(raw_file, f"manifest files[{index}]")
        source_path = _require_text(item.get("path"), f"manifest files[{index}].path")
        if source_path in seen:
            raise ValueError(f"duplicate manifest source path: {source_path}")
        seen.add(source_path)
        classification = _require_text(
            item.get("classification"),
            f"manifest files[{index}].classification",
        )
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(
                f"unsupported source classification {classification!r} for {source_path}"
            )
        actual_sha = sha256(_source_bytes(root, source_path, source_loader)).hexdigest()
        declared_sha = _require_sha(
            item.get("sha256"), f"manifest files[{index}].sha256"
        )
        if actual_sha != declared_sha:
            raise ValueError(
                f"source hash mismatch for {source_path}: expected {declared_sha}, "
                f"got {actual_sha}"
            )
        if classification == "mixed":
            regions = item.get("normative_regions")
            if not isinstance(regions, list) or not regions:
                raise ValueError(
                    f"mixed source {source_path} must declare normative_regions"
                )
            anchors: set[str] = set()
            for region_index, raw_region in enumerate(regions):
                region = (
                    raw_region
                    if isinstance(raw_region, Mapping)
                    else {"anchor": raw_region}
                )
                anchor = _require_text(
                    region.get("anchor"),
                    f"{source_path}.normative_regions[{region_index}].anchor",
                )
                if anchor in anchors:
                    raise ValueError(f"duplicate normative region anchor {anchor!r}")
                anchors.add(anchor)
        result.append(item)
    return result


def validate_manifest(
    manifest: Mapping[str, Any],
    root: str | Path | None = None,
    *,
    source_loader: SourceLoader | None = None,
) -> None:
    """Validate manifest structure and all declared source hashes."""

    root_path = _as_root(root)
    _manifest_files(manifest, root_path, source_loader=source_loader)


def _strip_statement_prefix(line: str) -> str:
    statement = line.strip()
    statement = re.sub(r"^\s*>\s?", "", statement)
    statement = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", statement)
    statement = re.sub(r"^\s*\[[ xX]\]\s+", "", statement)
    return statement.strip()


def _region_bounds(
    lines: list[str],
    source_path: str,
    region: Mapping[str, Any],
) -> tuple[str, int, int]:
    anchor = _require_text(region.get("anchor"), f"{source_path} region anchor")
    if any(key in region for key in ("start_line", "end_line", "start", "end")):
        raise ValueError(
            f"normative region {anchor!r} must use stable marker pairs, not line bounds"
        )

    start: int | None = None
    end: int | None = None
    for index, line in enumerate(lines):
        start_match = NORMATIVE_START.match(line)
        if start_match and start_match.group(1) == anchor:
            if start is not None:
                raise ValueError(f"duplicate normative start marker {anchor!r}")
            start = index + 1
            continue
        end_match = NORMATIVE_END.match(line)
        if end_match and end_match.group(1) == anchor:
            if start is None:
                raise ValueError(f"normative end marker precedes start for {anchor!r}")
            if end is not None:
                raise ValueError(f"duplicate normative end marker {anchor!r}")
            end = index
    if start is None or end is None or end < start:
        raise ValueError(
            f"normative region {anchor!r} in {source_path} lacks a valid marker pair"
        )
    return anchor, start, end


def _extract_statements(
    lines: list[str],
    source_path: str,
    *,
    regions: Iterable[tuple[str, int, int]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for anchor, start, end in regions:
        in_fence = False
        pending_requirement_anchor: str | None = None
        seen_requirement_anchors: set[str] = set()
        for line_number in range(start, end):
            line = lines[line_number]
            if line.strip().startswith("```") or line.strip().startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            marker = REQUIREMENT_MARKER.match(line)
            if marker:
                requirement_anchor = marker.group(1)
                if pending_requirement_anchor is not None:
                    raise ValueError(
                        f"requirement anchor {pending_requirement_anchor!r} in "
                        f"{source_path} is not attached to a statement"
                    )
                if requirement_anchor in seen_requirement_anchors:
                    raise ValueError(
                        f"duplicate requirement anchor {requirement_anchor!r} in "
                        f"{source_path}"
                    )
                pending_requirement_anchor = requirement_anchor
                seen_requirement_anchors.add(requirement_anchor)
                continue
            statement = _strip_statement_prefix(line)
            if not statement or statement.startswith("<!--"):
                continue
            is_list_statement = bool(
                re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|\[[ xX]\]\s+)", line)
            )
            is_table_statement = "|" in statement and not re.fullmatch(
                r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*",
                statement,
            )
            is_normative_candidate = bool(
                pending_requirement_anchor
                or NORMATIVE_WORD.search(statement)
                or is_list_statement
                or is_table_statement
            )
            if not is_normative_candidate:
                continue
            if pending_requirement_anchor is None:
                raise ValueError(
                    f"normative statement in {source_path}:{line_number + 1} lacks "
                    "an explicit requirement anchor"
                )
            source_anchor = f"{anchor}:{pending_requirement_anchor}"
            statement_anchor = pending_requirement_anchor
            pending_requirement_anchor = None
            statement_hash = sha256(statement.encode("utf-8")).hexdigest()
            logical_id = _requirement_logical_id(source_path, source_anchor)
            output.append(
                {
                    "id": f"{logical_id}-v1",
                    "logical_id": logical_id,
                    "version": 1,
                    "kind": "normative",
                    "classification": "approved_normative",
                    "source_path": source_path,
                    "source_anchor": source_anchor,
                    "source_region_anchor": anchor,
                    "source_statement_anchor": statement_anchor,
                    "statement": statement,
                    "statement_sha256": statement_hash,
                    "source_sha256": None,
                    "source_file_sha256": None,
                    "source_line": line_number + 1,
                }
            )
        if pending_requirement_anchor is not None:
            raise ValueError(
                f"requirement anchor {pending_requirement_anchor!r} in {source_path} "
                "is not attached to a statement"
            )
    return output


def _requirement_logical_id(source_path: str, source_anchor: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", source_path.lower()).strip("-")
    anchor = re.sub(r"[^a-z0-9]+", "-", source_anchor.lower()).strip("-")
    return f"V2-REQ-{slug}-{anchor}"


def build_source_requirements(
    manifest: Mapping[str, Any],
    *,
    root: str | Path | None = None,
    source_loader: SourceLoader | None = None,
) -> list[dict[str, Any]]:
    """Extract the complete source set represented by a baseline manifest."""

    root_path = _as_root(root)
    files = _manifest_files(manifest, root_path, source_loader=source_loader)
    requirements: list[dict[str, Any]] = []
    for raw_file in files:
        source_path = str(raw_file["path"])
        classification = str(raw_file["classification"])
        if classification in EXCLUDED_CLASSIFICATIONS:
            continue
        try:
            lines = (
                _source_bytes(root_path, source_path, source_loader)
                .decode("utf-8-sig")
                .splitlines()
            )
        except UnicodeError as exc:
            raise ValueError(f"source file is not UTF-8 text: {source_path}") from exc
        if classification == "mixed":
            regions = []
            for raw_region in raw_file["normative_regions"]:
                region = (
                    raw_region
                    if isinstance(raw_region, Mapping)
                    else {"anchor": raw_region}
                )
                regions.append(_region_bounds(lines, source_path, region))
        else:
            regions = [("root", 0, len(lines))]
        extracted = _extract_statements(lines, source_path, regions=regions)
        for item in extracted:
            item["source_sha256"] = str(raw_file["sha256"]).lower()
            item["source_file_sha256"] = str(raw_file["sha256"]).lower()
            item["kind"] = "gate" if classification == "proposed_gate" else "normative"
            item["classification"] = classification
            requirements.append(item)

    ids = [item["id"] for item in requirements]
    if len(ids) != len(set(ids)):
        raise ValueError("source extraction produced duplicate requirement IDs")
    anchors = [(item["source_path"], item["source_anchor"]) for item in requirements]
    if len(anchors) != len(set(anchors)):
        raise ValueError("source extraction produced duplicate source anchors")
    return requirements


def _placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    if not normalized:
        return True
    if normalized in {"none", "null", "n/a", "na", "-", "_"}:
        return True
    return any(word in normalized for word in PLACEHOLDER_WORDS)


def _require_concrete(value: Any, name: str) -> str:
    text = _require_text(value, name)
    if _placeholder(text):
        raise ValueError(f"{name} contains a placeholder or catch-all value")
    return text


def _validate_proof(entry: Mapping[str, Any], prefix: str) -> None:
    classification = entry.get("classification")
    proof_classification = _require_concrete(
        entry.get("proof_classification"), f"{prefix}.proof_classification"
    )
    final_target = _require_concrete(
        entry.get("final_proof_target"), f"{prefix}.final_proof_target"
    )
    environment = _require_concrete(
        entry.get("required_environment"), f"{prefix}.required_environment"
    )
    if classification == "proposed_gate" or proof_classification == "production":
        if final_target != "hosted-production" or environment != "hosted-production":
            raise ValueError(
                f"{prefix} proposed/production proof requires hosted-production"
            )
    for field in ("intended_red", "intended_green"):
        value = _require_mapping(entry.get(field), f"{prefix}.{field}")
        _require_concrete(value.get("test"), f"{prefix}.{field}.test")
        _require_concrete(value.get("command"), f"{prefix}.{field}.command")
        if field == "intended_red":
            _require_concrete(
                value.get("expected_missing_behavior"),
                f"{prefix}.{field}.expected_missing_behavior",
            )
    evidence = entry.get("observed_evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError(f"{prefix}.observed_evidence must be an object")
    for key in ("red", "green", "final"):
        if key not in evidence:
            raise ValueError(f"{prefix}.observed_evidence missing {key}")
    _reject_bad_evidence(evidence, prefix + ".observed_evidence")


def _reject_bad_evidence(value: Any, prefix: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_bad_evidence(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_bad_evidence(child, f"{prefix}[{index}]")
    elif isinstance(value, str):
        normalized = value.strip().lower()
        bad = ("fixture", "local-only", "indirect proof", "catch-all", "placeholder")
        if any(token in normalized for token in bad):
            raise ValueError(f"{prefix} contains non-production or indirect evidence")


def _validate_owner_timestamp(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a timezone-aware ISO-8601 timestamp")
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{name} must be a timezone-aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware ISO-8601 timestamp")


def _validate_implementation_note_path(value: Any, name: str) -> str:
    text = _require_concrete(value, name)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{name} must stay inside the repository")
    if path.suffix.lower() != ".md" or path.parts[:3] != (
        "docs",
        "v2",
        "implementation",
    ):
        raise ValueError(f"{name} must be a Markdown file under docs/v2/implementation")
    return path.as_posix()


def _validate_review_dispositions(value: Any, prefix: str) -> None:
    dispositions = _require_mapping(value, prefix)
    required = ("specification", "code_quality", "final_attestation")
    for name in required:
        if name not in dispositions:
            raise ValueError(f"{prefix} missing {name}")
        disposition = dispositions[name]
        if disposition is None:
            continue
        item = _require_mapping(disposition, f"{prefix}.{name}")
        _require_concrete(item.get("reviewer"), f"{prefix}.{name}.reviewer")
        result = _require_concrete(item.get("result"), f"{prefix}.{name}.result")
        if result not in {"approved", "rejected"}:
            raise ValueError(f"{prefix}.{name}.result must be approved or rejected")
        _validate_owner_timestamp(
            item.get("reviewed_at"), f"{prefix}.{name}.reviewed_at"
        )
        _require_sha(item.get("candidate_sha"), f"{prefix}.{name}.candidate_sha")
        findings = item.get("findings")
        if not isinstance(findings, list):
            raise ValueError(f"{prefix}.{name}.findings must be a list")


def validate_registry(
    registry: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    root: str | Path | None = None,
    source_loader: SourceLoader | None = None,
) -> None:
    """Validate registry coverage and every frozen requirement mapping."""

    if registry.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"registry schema_version must be {SCHEMA_VERSION!r}")
    expected_sha = _require_sha(manifest.get("normative_sha"), "manifest normative_sha")
    if registry.get("normative_sha") != expected_sha:
        raise ValueError("registry normative_sha does not match manifest")
    if registry.get("manifest_generation") != manifest.get("generation"):
        raise ValueError("registry manifest_generation does not match manifest")
    requirements = registry.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("registry requirements must be a non-empty list")

    expected = build_source_requirements(
        manifest, root=root, source_loader=source_loader
    )
    expected_by_id = {item["id"]: item for item in expected}
    actual_by_id: dict[str, Mapping[str, Any]] = {}
    indexed_entries: list[Mapping[str, Any]] = []
    for index, raw_entry in enumerate(requirements):
        entry = _require_mapping(raw_entry, f"registry requirements[{index}]")
        identifier = _require_text(entry.get("id"), f"requirements[{index}].id")
        if identifier in actual_by_id:
            raise ValueError(f"duplicate requirement ID: {identifier}")
        actual_by_id[identifier] = entry
        indexed_entries.append(entry)

    missing = sorted(set(expected_by_id) - set(actual_by_id))
    if missing:
        raise ValueError("missing requirement IDs: " + ", ".join(missing))
    expected_order = [item["id"] for item in expected]
    actual_order = [str(item["id"]) for item in indexed_entries]
    if actual_order != expected_order:
        raise ValueError(
            "registry requirement order must match deterministic source extraction"
        )

    for index, entry in enumerate(indexed_entries):
        identifier = str(entry["id"])
        _require_concrete(
            entry.get("source_path"), f"requirements[{index}].source_path"
        )
        source_anchor = _require_concrete(
            entry.get("source_anchor"), f"requirements[{index}].source_anchor"
        )
        if "*" in source_anchor or source_anchor.lower() in {"all", "meta"}:
            raise ValueError(f"requirements[{index}] uses a catch-all source anchor")
        if entry.get("classification") in EXCLUDED_CLASSIFICATIONS:
            raise ValueError(
                f"requirements[{index}] references an informative/verified/superseded source"
            )
        expected_entry = expected_by_id.get(identifier)
        if expected_entry is None:
            raise ValueError(f"unexpected requirement ID: {identifier}")
        for field in (
            "logical_id",
            "version",
            "kind",
            "classification",
            "source_path",
            "source_anchor",
            "source_region_anchor",
            "source_statement_anchor",
            "statement",
            "statement_sha256",
            "source_sha256",
            "source_file_sha256",
        ):
            if entry.get(field) != expected_entry.get(field):
                raise ValueError(
                    f"requirement {identifier} does not match manifest field {field}"
                )
        if _placeholder(entry.get("statement")):
            raise ValueError(f"requirement {identifier} has a placeholder statement")
        task = entry.get("implementation_task")
        if not isinstance(task, int) or isinstance(task, bool) or task < 1:
            raise ValueError(
                f"requirement {identifier} has invalid implementation_task"
            )
        _require_concrete(
            entry.get("implementation_slice"),
            f"requirement {identifier}.implementation_slice",
        )
        _validate_implementation_note_path(
            entry.get("implementation_note_path"),
            f"requirement {identifier}.implementation_note_path",
        )
        role = _require_concrete(
            entry.get("accountable_role"),
            f"requirement {identifier}.accountable_role",
        )
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*", role):
            raise ValueError(
                f"requirement {identifier}.accountable_role is not concrete"
            )
        owner = entry.get("owner_agent_id")
        if owner is not None:
            _require_concrete(owner, f"requirement {identifier}.owner_agent_id")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{2,127}", str(owner)):
                raise ValueError(
                    f"requirement {identifier}.owner_agent_id is not concrete"
                )
            _validate_owner_timestamp(
                entry.get("owner_assigned_at"),
                f"requirement {identifier}.owner_assigned_at",
            )
        elif entry.get("owner_assigned_at") is not None:
            raise ValueError(
                f"requirement {identifier}.owner_assigned_at requires an owner_agent_id"
            )
        _validate_proof(entry, f"requirement {identifier}")
        _validate_review_dispositions(
            entry.get("review_dispositions"),
            f"requirement {identifier}.review_dispositions",
        )


def build_registry(
    manifest: Mapping[str, Any],
    *,
    root: str | Path | None = None,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and re-emit source fields while requiring reviewed mappings.

    Task ownership and proof targets are governance decisions.  The builder is
    intentionally unable to infer them from prose or source classification.
    """

    sources = build_source_requirements(manifest, root=root)
    if existing is None:
        raise ValueError(
            "every requirement needs an explicit reviewed mapping; "
            "the registry builder does not infer task or proof ownership"
        )
    raw_requirements = existing.get("requirements")
    if not isinstance(raw_requirements, list):
        raise ValueError("explicit reviewed mappings must contain requirements")
    existing_by_id: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(raw_requirements):
        if not isinstance(item, Mapping) or not item.get("id"):
            raise ValueError(
                f"explicit reviewed mapping requirements[{index}] is invalid"
            )
        identifier = str(item["id"])
        if identifier in existing_by_id:
            raise ValueError(f"duplicate explicit reviewed mapping: {identifier}")
        existing_by_id[identifier] = item
    source_ids = {source["id"] for source in sources}
    orphaned = sorted(set(existing_by_id) - source_ids)
    if orphaned:
        raise ValueError(
            "explicit reviewed mappings reference removed requirements: "
            + ", ".join(orphaned)
        )
    entries: list[dict[str, Any]] = []
    for source in sources:
        previous = existing_by_id.get(source["id"])
        if previous is None:
            raise ValueError(
                f"requirement {source['id']} has no explicit reviewed mapping"
            )
        entry = deepcopy(dict(previous))
        for field in (
            "id",
            "logical_id",
            "version",
            "kind",
            "classification",
            "source_path",
            "source_anchor",
            "source_region_anchor",
            "source_statement_anchor",
            "statement",
            "statement_sha256",
            "source_sha256",
            "source_file_sha256",
        ):
            if entry.get(field) != source.get(field):
                raise ValueError(
                    f"requirement {source['id']} source drift requires an explicit "
                    f"registry transition: {field}"
                )
        entry["source_line"] = source["source_line"]
        entries.append(entry)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "normative_sha": str(manifest["normative_sha"]).lower(),
        "manifest_generation": manifest["generation"],
        "requirements": entries,
    }
    if isinstance(manifest.get("review_chain"), list) and manifest.get("review_chain"):
        result["review_chain"] = deepcopy(manifest["review_chain"])
    return result


def registry_sha256(registry: Mapping[str, Any]) -> str:
    """Hash the canonical registry representation, excluding no data fields."""

    canonical = json.dumps(
        registry,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def transition_registry_gate(
    registry: Mapping[str, Any],
    *,
    previous_manifest: Mapping[str, Any],
    next_manifest: Mapping[str, Any],
    promoted_path: str,
    root: str | Path | None = None,
    previous_source_loader: SourceLoader | None = None,
    next_source_loader: SourceLoader | None = None,
) -> dict[str, Any]:
    """Promote one reviewed gate while preserving its stable requirement IDs."""

    next_sha = _require_sha(
        next_manifest.get("normative_sha"), "next manifest normative_sha"
    )
    previous_sha = _require_sha(
        previous_manifest.get("normative_sha"), "previous manifest normative_sha"
    )
    if next_sha == previous_sha:
        raise ValueError("gate transition must create a new NORMATIVE_SHA")
    if next_manifest.get("generation") != previous_manifest.get("generation", 0) + 1:
        raise ValueError("gate transition generation must increase by exactly one")
    try:
        from tools.v2.transition_normative_baseline import validate_review_chain
    except ModuleNotFoundError:  # Direct execution from tools/v2.
        from transition_normative_baseline import validate_review_chain  # type: ignore[no-redef]

    validate_review_chain(next_manifest.get("review_chain"), candidate_sha=next_sha)
    if root is None:
        raise ValueError(
            "gate transition requires repository source validation; root is mandatory"
        )
    if root is not None:
        validate_registry(
            registry,
            previous_manifest,
            root=root,
            source_loader=previous_source_loader,
        )
        previous_sources = build_source_requirements(
            previous_manifest,
            root=root,
            source_loader=previous_source_loader,
        )
        next_sources = build_source_requirements(
            next_manifest,
            root=root,
            source_loader=next_source_loader,
        )
    else:
        # A transition is also used by the bootstrap tests with a synthetic
        # manifest whose files live outside the process cwd.  The registry is
        # already the frozen source snapshot in that case; use its hashes and
        # anchors rather than silently reading another repository.
        previous_sources = [
            dict(item)
            for item in registry.get("requirements", [])
            if isinstance(item, Mapping)
        ]
        next_sources = deepcopy(previous_sources)
        for item in next_sources:
            if item.get("source_path") == promoted_path:
                item["kind"] = "normative"
                item["classification"] = "approved_normative"
        manifest_files = previous_manifest.get("files")
        next_files = next_manifest.get("files")
        if not isinstance(manifest_files, list) or not isinstance(next_files, list):
            raise ValueError("manifest files must be lists for gate transition")
        previous_file = next(
            (
                item
                for item in manifest_files
                if isinstance(item, Mapping) and item.get("path") == promoted_path
            ),
            None,
        )
        next_file = next(
            (
                item
                for item in next_files
                if isinstance(item, Mapping) and item.get("path") == promoted_path
            ),
            None,
        )
        if previous_file is None or next_file is None:
            raise ValueError(f"promoted path is not a complete source: {promoted_path}")
        if previous_file.get("classification") != "proposed_gate":
            raise ValueError("only proposed_gate sources can be promoted")
        if next_file.get("classification") != "approved_normative":
            raise ValueError(
                "next manifest must promote the gate to approved_normative"
            )
        if previous_file.get("sha256") != next_file.get("sha256"):
            raise ValueError("promoted gate source content changed during transition")

    previous_promoted = [
        item for item in previous_sources if item.get("source_path") == promoted_path
    ]
    next_promoted = [
        item for item in next_sources if item.get("source_path") == promoted_path
    ]
    if not previous_promoted or not next_promoted:
        raise ValueError(f"promoted path is not a complete source: {promoted_path}")
    if not all(
        item.get("classification") == "proposed_gate" for item in previous_promoted
    ):
        raise ValueError("only proposed_gate sources can be promoted")
    if not all(
        item.get("classification") == "approved_normative" for item in next_promoted
    ):
        raise ValueError("next manifest must promote the gate to approved_normative")
    previous_by_statement = {
        item["statement_sha256"]: item for item in previous_promoted
    }
    next_by_statement = {item["statement_sha256"]: item for item in next_promoted}
    if set(previous_by_statement) != set(next_by_statement):
        raise ValueError("promoted gate statements changed during transition")

    transitioned = deepcopy(dict(registry))
    transitioned["normative_sha"] = next_sha
    transitioned["manifest_generation"] = next_manifest.get("generation")
    if isinstance(next_manifest.get("review_chain"), list):
        transitioned["review_chain"] = deepcopy(next_manifest["review_chain"])
    next_by_id = {item["id"]: item for item in next_sources}
    current_ids = {
        str(item.get("id"))
        for item in transitioned["requirements"]
        if isinstance(item, Mapping)
    }
    if current_ids != set(next_by_id):
        raise ValueError("gate transition cannot add or remove requirement IDs")
    for entry in transitioned["requirements"]:
        expected = next_by_id.get(entry["id"])
        if expected is None:
            raise ValueError(f"transition would orphan requirement ID {entry['id']}")
        for field in (
            "logical_id",
            "version",
            "kind",
            "classification",
            "source_path",
            "source_anchor",
            "source_region_anchor",
            "source_statement_anchor",
            "statement",
            "statement_sha256",
            "source_sha256",
            "source_file_sha256",
            "source_line",
        ):
            entry[field] = expected[field]
    if root is not None:
        validate_registry(
            transitioned,
            next_manifest,
            root=root,
            source_loader=next_source_loader,
        )
    return transitioned


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--transition-gate", help="stable gate ID/path to check")
    return parser.parse_args()


def _load_git_document(root: Path, treeish: str, path: Path) -> dict[str, Any]:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"Git document path escapes repository: {path}") from exc
    if ".." in candidate.parts:
        raise ValueError(f"Git document path escapes repository: {path}")
    relative = candidate.as_posix()
    try:
        raw = subprocess.run(
            ["git", "show", f"{treeish}:{relative}"],
            check=True,
            capture_output=True,
            cwd=root,
        ).stdout
        value = json.loads(raw.decode("utf-8-sig"))
    except (
        OSError,
        subprocess.CalledProcessError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(f"cannot load Git document {treeish}:{relative}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Git document {treeish}:{relative} must contain an object")
    return value


def _git_source_loader(root: Path, treeish: str) -> SourceLoader:
    def load(source_path: str) -> bytes:
        path = Path(source_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"source path escapes repository root: {source_path}")
        try:
            return subprocess.run(
                ["git", "show", f"{treeish}:{path.as_posix()}"],
                check=True,
                capture_output=True,
                cwd=root,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError(
                f"source blob is unavailable in {treeish}: {source_path}"
            ) from exc

    return load


def main() -> int:
    args = _parse_args()
    manifest = load_document(args.manifest)
    root = Path.cwd().resolve()
    existing = load_document(args.registry) if args.registry.exists() else None
    if args.check:
        if existing is None:
            raise ValueError(f"registry does not exist: {args.registry}")
        if args.transition_gate:
            previous_manifest = _load_git_document(
                root,
                "HEAD",
                args.manifest,
            )
            if previous_manifest.get("normative_sha") == manifest.get("normative_sha"):
                raise ValueError("gate transition must create a new NORMATIVE_SHA")
            matches = [
                item
                for item in existing["requirements"]
                if item["id"] == args.transition_gate
                or args.transition_gate.lower() in str(item["source_path"]).lower()
            ]
            if not matches:
                raise ValueError(f"transition gate not found: {args.transition_gate}")
            proposed_paths = {
                str(item["source_path"])
                for item in matches
                if item.get("classification") == "proposed_gate"
            }
            if len(proposed_paths) != 1:
                raise ValueError(
                    "transition gate must identify one proposed_gate source"
                )
            previous_sha = str(previous_manifest["normative_sha"])
            next_sha = str(manifest["normative_sha"])
            transitioned = transition_registry_gate(
                existing,
                previous_manifest=previous_manifest,
                next_manifest=manifest,
                promoted_path=next(iter(proposed_paths)),
                root=root,
                previous_source_loader=_git_source_loader(root, previous_sha),
                next_source_loader=_git_source_loader(root, next_sha),
            )
            validate_registry(
                transitioned,
                manifest,
                root=root,
                source_loader=_git_source_loader(root, next_sha),
            )
            write_document(args.registry, transitioned)
            return 0
        validate_registry(existing, manifest, root=root)
        return 0
    generated = build_registry(manifest, root=root, existing=existing)
    validate_registry(generated, manifest, root=root)
    write_document(args.registry, generated)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc
