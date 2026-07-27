from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "v2" / "run_local_image_supply_chain_gate.py"
SPEC = importlib.util.spec_from_file_location("local_image_supply_chain_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_runner_uses_docker_scout_local_image_and_fails_closed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert '"docker", "build"' in source
    for token in ('"docker"', '"scout"', '"sbom"'):
        assert token in source
    assert 'f"local://{before[\'image_id\']}"' in source
    assert '"cyclonedx"' in source
    assert "image_identity_changed_during_scan" in source
    assert "source_changed_during_image_scan" in source
    assert "secret_pattern_detected_in_evidence" in source
    assert "environment_files_excluded_without_reading" in source
    assert "execution_ledger_excluded_as_self_referential_record" in source
    assert "container_image_vulnerability_audit" in source
    assert "artifact_signature" in source
    assert "release_attestation" in source
    assert "production_release" in source
    assert "docker scout cves" not in source
    assert "docker push" not in source
    assert "docker login" not in source
    assert '"TEMP": str(scout_temp)' in source
    assert "docker_scout_temp_cleanup_failed" in source


def test_source_manifest_never_reads_environment_files(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("APP = True\n", encoding="utf-8")
    (tmp_path / ".env").write_text("REAL_SECRET=must-not-appear\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text(
        "EXAMPLE_SECRET=must-not-appear\n", encoding="utf-8"
    )
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / ".env.production").write_text(
        "PRODUCTION_SECRET=must-not-appear\n", encoding="utf-8"
    )
    ledger = tmp_path / "docs" / "v2" / "18-v2-execution-ledger.md"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("self-referential execution record\n", encoding="utf-8")

    digest, content, count = MODULE._build_source_manifest(
        tmp_path,
        [
            "app.py",
            ".env",
            ".env.example",
            "nested/.env.production",
            "docs/v2/18-v2-execution-ledger.md",
        ],
    )

    assert len(digest) == 64
    assert count == 1
    assert "app.py" in content
    assert ".env" not in content
    assert "18-v2-execution-ledger.md" not in content
    assert "self-referential" not in content
    assert "must-not-appear" not in content

    manifest = tmp_path / "source-manifest.sha256"
    MODULE._write_text(manifest, content)
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == digest
    assert b"\r\n" not in manifest.read_bytes()


def test_cyclonedx_validation_binds_root_purl_to_image(tmp_path: Path) -> None:
    image_id = "sha256:" + "a" * 64
    sbom = tmp_path / "image.cdx.json"
    sbom.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "serialNumber": "urn:uuid:test",
                "metadata": {
                    "component": {
                        "type": "container",
                        "name": "fixture",
                        "version": "local",
                        "purl": f"pkg:oci/fixture@{image_id}",
                    }
                },
                "components": [{"type": "application", "purl": "pkg:pypi/a@1"}],
                "dependencies": [{"ref": "pkg:pypi/a@1"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = MODULE._validate_cyclonedx(sbom, image_id)

    assert result["components"] == 1
    assert result["dependencies"] == 1
    assert result["components_with_purl"] == 1

    with pytest.raises(MODULE.GateError, match="root_purl_not_bound"):
        MODULE._validate_cyclonedx(sbom, "sha256:" + "b" * 64)
