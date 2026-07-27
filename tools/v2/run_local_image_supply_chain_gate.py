from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
EXECUTION_LEDGER_PATH = PurePosixPath("docs/v2/18-v2-execution-ledger.md")
SECRET_PATTERNS = (
    re.compile(r"Bearer [A-Za-z0-9._~+/-]{20,}", re.IGNORECASE),
    re.compile(r"postgres(?:ql)?(?:\+asyncpg)?://[^:]+:[^@\[]+@", re.IGNORECASE),
    re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.IGNORECASE),
)


class GateError(RuntimeError):
    def __init__(self, reason: str, *, exit_code: int = 70) -> None:
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code


def _run(
    command: list[str],
    *,
    timeout: int = 300,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GateError(f"required_tool_missing:{command[0]}", exit_code=69) from exc
    except subprocess.TimeoutExpired as exc:
        raise GateError(f"command_timeout:{command[0]}") from exc


def _required_run(
    command: list[str],
    *,
    reason: str,
    timeout: int = 300,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = _run(command, timeout=timeout, environment=environment)
    if completed.returncode != 0:
        raise GateError(reason)
    return completed


def _is_environment_path(relative: str) -> bool:
    return any(
        part == ".env" or part.startswith(".env.")
        for part in PurePosixPath(relative).parts
    )


def _is_source_identity_excluded(relative: str) -> bool:
    return (
        _is_environment_path(relative)
        or PurePosixPath(relative) == EXECUTION_LEDGER_PATH
    )


def _git_paths() -> list[str]:
    completed = _required_run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        reason="source_inventory_failed",
    )
    return sorted(
        path
        for path in completed.stdout.split("\0")
        if path and not _is_source_identity_excluded(path)
    )


def _build_source_manifest(
    repository_root: Path,
    relative_paths: list[str],
) -> tuple[str, str, int]:
    entries: list[str] = []
    for relative in relative_paths:
        if _is_source_identity_excluded(relative):
            continue
        candidate = repository_root / relative
        if not candidate.is_file():
            continue
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        entries.append(f"{digest}  {PurePosixPath(relative)}")
    content = "\n".join(entries) + "\n"
    return hashlib.sha256(content.encode("utf-8")).hexdigest(), content, len(entries)


def _image_identity(reference: str) -> dict[str, Any]:
    completed = _required_run(
        ["docker", "image", "inspect", reference],
        reason="image_inspect_failed",
    )
    try:
        images = json.loads(completed.stdout)
        image = images[0]
        image_id = image["Id"]
        platform = f"{image['Os']}/{image['Architecture']}"
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise GateError("image_inspect_invalid_json") from exc
    repo_digests = image.get("RepoDigests") or []
    if not isinstance(repo_digests, list) or not all(
        isinstance(item, str) for item in repo_digests
    ):
        raise GateError("image_inspect_invalid_repo_digests")
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        raise GateError("image_inspect_invalid_id")
    return {
        "requested_reference": reference,
        "image_id": image_id,
        "repo_digests": sorted(repo_digests),
        "platform": platform,
        "created": image.get("Created"),
        "immutable_repo_digest": bool(repo_digests),
    }


def _validate_cyclonedx(path: Path, image_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError("image_sbom_invalid_json") from exc
    if payload.get("bomFormat") != "CycloneDX":
        raise GateError("image_sbom_not_cyclonedx")
    spec_version = payload.get("specVersion")
    if not isinstance(spec_version, str) or not spec_version:
        raise GateError("image_sbom_missing_spec_version")
    components = payload.get("components")
    dependencies = payload.get("dependencies")
    if not isinstance(components, list) or not components:
        raise GateError("image_sbom_zero_components")
    if not isinstance(dependencies, list) or not dependencies:
        raise GateError("image_sbom_zero_dependencies")
    root_component = (payload.get("metadata") or {}).get("component") or {}
    root_purl = root_component.get("purl")
    image_hex = image_id.removeprefix("sha256:")
    if not isinstance(root_purl, str) or image_hex not in root_purl:
        raise GateError("image_sbom_root_purl_not_bound_to_image")
    purl_count = sum(
        1
        for component in components
        if isinstance(component, dict)
        and isinstance(component.get("purl"), str)
        and component["purl"]
    )
    if purl_count == 0:
        raise GateError("image_sbom_zero_purls")
    return {
        "format": "CycloneDX",
        "spec_version": spec_version,
        "serial_number": payload.get("serialNumber"),
        "root_component_type": root_component.get("type"),
        "root_component_name": root_component.get("name"),
        "root_component_version": root_component.get("version"),
        "root_purl": root_purl,
        "components": len(components),
        "dependencies": len(dependencies),
        "components_with_purl": purl_count,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _secret_match(files: list[Path]) -> bool:
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            return True
    return False


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _finalize(stage: Path, target: Path) -> None:
    for path in stage.iterdir():
        if path.is_file():
            try:
                path.chmod(0o600)
            except OSError:
                pass
    stage.replace(target)


def _failure_bundle(stage: Path, target: Path, error: GateError) -> None:
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(mode=0o700)
    _write_json(
        stage / "evidence-manifest.json",
        {
            "schema_version": "1.0",
            "status": "failed",
            "proof_level": "local-dirty-worktree-container-image-sbom",
            "failure_reason": error.reason,
            "does_not_prove": [
                "container_image_vulnerability_audit",
                "artifact_signature",
                "release_attestation",
                "production_release",
            ],
        },
    )
    _finalize(stage, target)


def _execute(image: str, stage: Path) -> dict[str, Any]:
    git_head = _required_run(
        ["git", "rev-parse", "HEAD"], reason="git_head_failed"
    ).stdout.strip()
    git_dirty = bool(
        _required_run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            reason="git_status_failed",
        ).stdout.strip()
    )
    source_before, source_content, source_count = _build_source_manifest(
        ROOT, _git_paths()
    )
    source_path = stage / "source-manifest.sha256"
    _write_text(source_path, source_content)

    build = _required_run(
        ["docker", "build", "--tag", image, "--file", "Dockerfile", "."],
        reason="image_build_failed",
        timeout=900,
    )
    build_path = stage / "build.log"
    _write_text(build_path, build.stdout + build.stderr)

    before = _image_identity(image)
    identity_path = stage / "image-identity.json"
    _write_json(identity_path, before)

    scout_version = _required_run(
        ["docker", "scout", "version"], reason="docker_scout_unavailable"
    )
    scout_version_match = re.search(r"^version:\s*(\S+)", scout_version.stdout, re.MULTILINE)
    if scout_version_match is None:
        raise GateError("docker_scout_version_unparseable")

    sbom_path = stage / "backend-image.cdx.json"
    scout_temp = stage / ".scout-tmp"
    scout_temp.mkdir(mode=0o700)
    scout_environment = os.environ.copy()
    scout_environment.update(
        {
            "TEMP": str(scout_temp),
            "TMP": str(scout_temp),
            "TMPDIR": str(scout_temp),
        }
    )
    scout = _required_run(
        [
            "docker",
            "scout",
            "sbom",
            "--format",
            "cyclonedx",
            "--output",
            str(sbom_path),
            f"local://{before['image_id']}",
        ],
        reason="image_sbom_generation_failed",
        timeout=900,
        environment=scout_environment,
    )
    scout_path = stage / "scout.log"
    _write_text(scout_path, scout.stdout + scout.stderr)
    shutil.rmtree(scout_temp, ignore_errors=True)
    if scout_temp.exists():
        raise GateError("docker_scout_temp_cleanup_failed")
    sbom = _validate_cyclonedx(sbom_path, before["image_id"])

    after = _image_identity(image)
    if after["image_id"] != before["image_id"]:
        raise GateError("image_identity_changed_during_scan")
    source_after, _, source_after_count = _build_source_manifest(ROOT, _git_paths())
    if source_after != source_before or source_after_count != source_count:
        raise GateError("source_changed_during_image_scan")

    generated_files = [
        source_path,
        build_path,
        identity_path,
        sbom_path,
        scout_path,
    ]
    if _secret_match(generated_files):
        raise GateError("secret_pattern_detected_in_evidence")

    artifact_hashes = {path.name: _sha256(path) for path in generated_files}
    summary = {
        "schema_version": "1.0",
        "status": "passed",
        "proof_level": "local-dirty-worktree-container-image-sbom",
        "source": {
            "git_head": git_head,
            "git_dirty": git_dirty,
            "manifest_sha256": source_before,
            "file_count": source_count,
            "stable_during_scan": True,
            "environment_files_excluded_without_reading": True,
            "execution_ledger_excluded_as_self_referential_record": True,
        },
        "image": before,
        "tools": {"docker_scout": scout_version_match.group(1)},
        "sbom": sbom,
        "artifact_sha256": artifact_hashes,
        "secret_pattern_matches": 0,
        "does_not_prove": [
            "committed_immutable_source_candidate",
            "registry_published_image_digest",
            "container_image_vulnerability_audit",
            "artifact_signature",
            "release_attestation",
            "production_release",
        ],
    }
    manifest_path = stage / "evidence-manifest.json"
    _write_json(manifest_path, summary)
    hash_targets = [*generated_files, manifest_path]
    hash_lines = [f"{_sha256(path)}  {path.name}" for path in hash_targets]
    _write_text(stage / "artifact-sha256.txt", "\n".join(hash_lines) + "\n")
    return summary


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    arguments = parser.parse_args()
    target = arguments.evidence_dir.resolve()
    if target.is_relative_to(ROOT):
        parser.error("--evidence-dir must be outside the repository")
    if target.exists():
        parser.error("--evidence-dir must not already exist")
    if not target.parent.is_dir():
        parser.error("--evidence-dir parent must exist")
    stage = target.parent / f".{target.name}.stage-{uuid4().hex}"
    stage.mkdir(mode=0o700)
    try:
        summary = _execute(arguments.image, stage)
    except GateError as error:
        _failure_bundle(stage, target, error)
        print(json.dumps({"status": "failed", "failure_reason": error.reason}))
        raise SystemExit(error.exit_code) from error
    _finalize(stage, target)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
