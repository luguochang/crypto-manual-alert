from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import subprocess
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
COSIGN_IMAGE = (
    "ghcr.io/sigstore/cosign/cosign:v2.4.3@sha256:"
    "c77247c92f4dfea851c70555738226498393e34e2f9ca83cb959e51c230e4ad7"
)
SECRET_PATTERNS = (
    re.compile(r"Bearer [A-Za-z0-9._~+/-]{20,}", re.IGNORECASE),
    re.compile(r"postgres(?:ql)?(?:\+asyncpg)?://[^:]+:[^@\[]+@", re.IGNORECASE),
    re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.IGNORECASE),
)
HASH_LINE = re.compile(r"^([a-f0-9]{64})  ([A-Za-z0-9._-]+)$")


class GateError(RuntimeError):
    def __init__(self, reason: str, *, exit_code: int = 70) -> None:
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code


def _run(
    command: list[str],
    *,
    environment: dict[str, str] | None = None,
    timeout: int = 300,
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


def _required(
    command: list[str],
    *,
    reason: str,
    environment: dict[str, str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    completed = _run(command, environment=environment, timeout=timeout)
    if completed.returncode != 0:
        raise GateError(reason)
    return completed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _verify_subject_bundle(evidence_dir: Path) -> dict[str, Any]:
    manifest_path = evidence_dir / "evidence-manifest.json"
    hashes_path = evidence_dir / "artifact-sha256.txt"
    if not manifest_path.is_file() or not hashes_path.is_file():
        raise GateError("subject_evidence_missing_manifest_or_hashes")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError("subject_manifest_invalid_json") from exc
    if manifest.get("status") != "passed":
        raise GateError("subject_evidence_not_passed")
    if manifest.get("proof_level") != "local-dirty-worktree-container-image-sbom":
        raise GateError("subject_evidence_wrong_proof_level")
    lines = hashes_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise GateError("subject_hash_list_empty")
    verified: list[str] = []
    for line in lines:
        match = HASH_LINE.fullmatch(line)
        if match is None:
            raise GateError("subject_hash_list_invalid_line")
        expected, name = match.groups()
        relative = PurePosixPath(name)
        if relative.name != name or relative.is_absolute():
            raise GateError("subject_hash_list_unsafe_path")
        candidate = evidence_dir / name
        if not candidate.is_file() or _sha256(candidate) != expected:
            raise GateError("subject_hash_verification_failed")
        verified.append(name)
    image = manifest.get("image") or {}
    sbom = manifest.get("sbom") or {}
    image_id = image.get("image_id")
    root_purl = sbom.get("root_purl")
    if not isinstance(image_id, str) or not isinstance(root_purl, str):
        raise GateError("subject_manifest_missing_image_binding")
    if image_id.removeprefix("sha256:") not in root_purl:
        raise GateError("subject_manifest_image_binding_mismatch")
    return {
        "manifest": manifest,
        "hashes_path": hashes_path,
        "verified_artifacts": verified,
        "image_id": image_id,
        "root_purl": root_purl,
    }


def _cosign_identity() -> dict[str, Any]:
    _required(["docker", "pull", COSIGN_IMAGE], reason="cosign_image_pull_failed", timeout=600)
    inspect = _required(
        ["docker", "image", "inspect", COSIGN_IMAGE],
        reason="cosign_image_inspect_failed",
    )
    try:
        image = json.loads(inspect.stdout)[0]
        image_id = image["Id"]
        repo_digests = image.get("RepoDigests") or []
        platform = f"{image['Os']}/{image['Architecture']}"
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise GateError("cosign_image_inspect_invalid_json") from exc
    expected_digest = COSIGN_IMAGE.rsplit("@", 1)[1]
    if not any(item.endswith(f"@{expected_digest}") for item in repo_digests):
        raise GateError("cosign_image_digest_mismatch")
    return {
        "reference": COSIGN_IMAGE,
        "image_id": image_id,
        "repo_digests": sorted(repo_digests),
        "platform": platform,
        "version": "v2.4.3",
    }


def _cosign_command(stage: Path, arguments: list[str]) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m",
        "--mount",
        f"type=bind,src={stage},dst=/work",
        "--env",
        "COSIGN_PASSWORD",
        COSIGN_IMAGE,
        *arguments,
    ]


def _secret_match(files: list[Path]) -> bool:
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            return True
    return False


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
            "proof_level": "local-ephemeral-key-cosign-blob-signature",
            "failure_reason": error.reason,
            "does_not_prove": [
                "registry_container_image_signature",
                "protected_signing_key_custody",
                "oidc_signing_identity",
                "transparency_log_inclusion",
                "release_attestation",
                "production_release",
            ],
        },
    )
    _finalize(stage, target)


def _execute(subject_evidence: Path, stage: Path) -> dict[str, Any]:
    subject = _verify_subject_bundle(subject_evidence)
    cosign = _cosign_identity()
    subject_path = stage / "signed-subject.sha256.txt"
    shutil.copyfile(subject["hashes_path"], subject_path)
    private_key = stage / "local-signing.key"
    public_key = stage / "local-signing.pub"
    signature = stage / "signed-subject.sig"
    tampered = stage / "tampered-subject.txt"
    password_environment = os.environ.copy()
    password_environment["COSIGN_PASSWORD"] = secrets.token_urlsafe(32)

    logs: list[str] = []
    generated = _required(
        _cosign_command(
            stage,
            ["generate-key-pair", "--output-key-prefix", "/work/local-signing"],
        ),
        reason="cosign_key_generation_failed",
        environment=password_environment,
    )
    logs.append(generated.stdout + generated.stderr)
    if not private_key.is_file() or not public_key.is_file():
        raise GateError("cosign_key_pair_missing")
    signed = _required(
        _cosign_command(
            stage,
            [
                "sign-blob",
                "--yes",
                "--tlog-upload=false",
                "--key",
                "/work/local-signing.key",
                "--output-signature",
                "/work/signed-subject.sig",
                "/work/signed-subject.sha256.txt",
            ],
        ),
        reason="cosign_blob_sign_failed",
        environment=password_environment,
    )
    logs.append(signed.stdout + signed.stderr)
    if not signature.is_file() or signature.stat().st_size == 0:
        raise GateError("cosign_signature_missing")
    verified = _required(
        _cosign_command(
            stage,
            [
                "verify-blob",
                "--offline",
                "--insecure-ignore-tlog",
                "--key",
                "/work/local-signing.pub",
                "--signature",
                "/work/signed-subject.sig",
                "/work/signed-subject.sha256.txt",
            ],
        ),
        reason="cosign_blob_verify_failed",
        environment=password_environment,
    )
    logs.append(verified.stdout + verified.stderr)

    shutil.copyfile(subject_path, tampered)
    with tampered.open("ab") as stream:
        stream.write(b"tampered\n")
    negative = _run(
        _cosign_command(
            stage,
            [
                "verify-blob",
                "--offline",
                "--insecure-ignore-tlog",
                "--key",
                "/work/local-signing.pub",
                "--signature",
                "/work/signed-subject.sig",
                "/work/tampered-subject.txt",
            ],
        ),
        environment=password_environment,
    )
    if negative.returncode == 0:
        raise GateError("cosign_tampered_subject_was_accepted")
    logs.append("tampered_subject_rejected=true\n")
    tampered.unlink()
    private_key.unlink()
    if private_key.exists():
        raise GateError("cosign_private_key_retained")

    log_path = stage / "cosign.log"
    _write_text(log_path, "".join(logs))
    generated_files = [subject_path, public_key, signature, log_path]
    if _secret_match(generated_files):
        raise GateError("secret_pattern_detected_in_signature_evidence")

    summary = {
        "schema_version": "1.0",
        "status": "passed",
        "proof_level": "local-ephemeral-key-cosign-blob-signature",
        "subject": {
            "source_evidence": str(subject_evidence),
            "source_evidence_proof_level": subject["manifest"]["proof_level"],
            "source_hash_list_sha256": _sha256(subject_path),
            "verified_source_artifacts": subject["verified_artifacts"],
            "image_id": subject["image_id"],
            "root_purl": subject["root_purl"],
        },
        "cosign": cosign,
        "verification": {
            "offline": True,
            "network_mode": "none",
            "tlog_upload": False,
            "positive_signature_verified": True,
            "tampered_subject_rejected": True,
            "private_key_retained": False,
            "secret_pattern_matches": 0,
        },
        "does_not_prove": [
            "registry_container_image_signature",
            "protected_signing_key_custody",
            "oidc_signing_identity",
            "transparency_log_inclusion",
            "release_attestation",
            "production_release",
        ],
    }
    manifest_path = stage / "evidence-manifest.json"
    _write_json(manifest_path, summary)
    hash_targets = [*generated_files, manifest_path]
    _write_text(
        stage / "artifact-sha256.txt",
        "\n".join(f"{_sha256(path)}  {path.name}" for path in hash_targets) + "\n",
    )
    return summary


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject-evidence", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    arguments = parser.parse_args()
    subject = arguments.subject_evidence.resolve()
    target = arguments.evidence_dir.resolve()
    if subject.is_relative_to(ROOT) or not subject.is_dir():
        parser.error("--subject-evidence must be an existing directory outside the repo")
    if target.is_relative_to(ROOT):
        parser.error("--evidence-dir must be outside the repository")
    if target.exists():
        parser.error("--evidence-dir must not already exist")
    if not target.parent.is_dir():
        parser.error("--evidence-dir parent must exist")
    stage = target.parent / f".{target.name}.stage-{uuid4().hex}"
    stage.mkdir(mode=0o700)
    try:
        summary = _execute(subject, stage)
    except GateError as error:
        _failure_bundle(stage, target, error)
        print(json.dumps({"status": "failed", "failure_reason": error.reason}))
        raise SystemExit(error.exit_code) from error
    _finalize(stage, target)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
