from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "v2" / "run_local_cosign_bundle_gate.py"
SPEC = importlib.util.spec_from_file_location("local_cosign_bundle_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_runner_uses_pinned_offline_cosign_and_deletes_private_key() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "cosign/cosign:v2.4.3@sha256:" in source
    assert "c77247c92f4dfea851c70555738226498393e34e2f9ca83cb959e51c230e4ad7" in source
    assert '"--network",\n        "none"' in source
    assert '"--read-only"' in source
    assert '"--cap-drop",\n        "ALL"' in source
    assert '"COSIGN_PASSWORD"' in source
    assert '"--tlog-upload=false"' in source
    assert '"--offline"' in source
    assert '"--insecure-ignore-tlog"' in source
    assert "cosign_tampered_subject_was_accepted" in source
    assert "private_key.unlink()" in source
    assert "cosign_private_key_retained" in source
    assert "registry_container_image_signature" in source
    assert "protected_signing_key_custody" in source
    assert "transparency_log_inclusion" in source
    assert "docker push" not in source
    assert "docker login" not in source


def _subject_bundle(root: Path) -> Path:
    artifact = root / "backend-image.cdx.json"
    artifact.write_text("{}\n", encoding="utf-8")
    manifest = root / "evidence-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "status": "passed",
                "proof_level": "local-dirty-worktree-container-image-sbom",
                "image": {"image_id": "sha256:" + "a" * 64},
                "sbom": {"root_purl": "pkg:oci/app@sha256:" + "a" * 64},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    hashes = root / "artifact-sha256.txt"
    hashes.write_text(
        f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}\n"
        f"{hashlib.sha256(manifest.read_bytes()).hexdigest()}  {manifest.name}\n",
        encoding="utf-8",
    )
    return root


def test_subject_bundle_requires_all_hashes_and_image_binding(tmp_path: Path) -> None:
    subject = _subject_bundle(tmp_path)

    result = MODULE._verify_subject_bundle(subject)

    assert result["image_id"] == "sha256:" + "a" * 64
    assert result["verified_artifacts"] == [
        "backend-image.cdx.json",
        "evidence-manifest.json",
    ]

    (subject / "backend-image.cdx.json").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(MODULE.GateError, match="hash_verification_failed"):
        MODULE._verify_subject_bundle(subject)


def test_subject_hash_list_rejects_unsafe_paths(tmp_path: Path) -> None:
    subject = _subject_bundle(tmp_path)
    (subject / "artifact-sha256.txt").write_text(
        f"{'a' * 64}  ../outside\n", encoding="utf-8"
    )

    with pytest.raises(MODULE.GateError, match="invalid_line|unsafe_path"):
        MODULE._verify_subject_bundle(subject)
