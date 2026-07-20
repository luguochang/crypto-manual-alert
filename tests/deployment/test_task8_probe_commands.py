import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHELL_PROBE = ROOT / "tools" / "v2" / "probe_product_api.sh"
NODE_PROBE = ROOT / "tools" / "v2" / "probe_protocol_v2.mjs"
IMAGE_VERIFIER = ROOT / "tools" / "v2" / "verify_agent_image.sh"


def _shell_probe() -> str:
    return SHELL_PROBE.read_text(encoding="utf-8")


def _shell_function(script: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n(?P<body>.*?)^\}}\n",
        script,
    )
    assert match is not None, f"probe must define {name}()"
    return match.group("body")


def _pytest_selectors(script: str) -> set[str]:
    return set(
        re.findall(
            r"tests/[A-Za-z0-9_./-]+\.py::(test_[A-Za-z0-9_]+)",
            script,
        )
    )


def _first_index(script: str, *needles: str) -> int:
    positions = [script.find(needle) for needle in needles]
    present = [position for position in positions if position >= 0]
    assert present, f"probe must contain one of: {', '.join(needles)}"
    return min(present)


def test_task8_probe_scripts_are_syntactically_valid_and_executable() -> None:
    assert SHELL_PROBE.stat().st_mode & 0o111
    assert NODE_PROBE.stat().st_mode & 0o111

    shell = subprocess.run(
        ["bash", "-n", str(SHELL_PROBE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    node = subprocess.run(
        ["node", "--check", str(NODE_PROBE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert shell.returncode == 0, shell.stderr
    assert node.returncode == 0, node.stderr


def test_task8_fixture_is_explicitly_separated_from_production_stack_profile() -> None:
    stack = (ROOT / "tools" / "v2" / "start_integration_stack.sh").read_text(
        encoding="utf-8"
    )
    probe = _shell_probe()

    assert 'V2_STACK_PROFILE="${V2_STACK_PROFILE:-production}"' in stack
    assert "production profile only accepts the canonical backend/langgraph.json" in stack
    assert "task8-multi-interrupt-qa" in stack
    assert 'export V2_STACK_PROFILE=task8-multi-interrupt-qa' in probe


def test_task8_probe_references_only_existing_test_files() -> None:
    script = _shell_probe()
    referenced = set(
        re.findall(r"(?:tests/[A-Za-z0-9_./-]+\.py)(?:::[A-Za-z0-9_]+)?", script)
    )

    assert referenced
    missing = [
        reference
        for reference in sorted(referenced)
        if not (ROOT / "backend" / reference.split("::", 1)[0]).is_file()
    ]
    assert missing == []


def test_task8_probe_requires_an_explicit_evidence_directory() -> None:
    script = _shell_probe()
    help_result = subprocess.run(
        ["bash", str(SHELL_PROBE), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert help_result.returncode == 0, help_result.stderr
    assert re.search(r"--evidence-dir(?:[ =](?:DIR|PATH))", help_result.stdout)
    assert re.search(r"(?m)^\s*--evidence-dir\)\s*$", script)
    assert re.search(r"(?m)^EVIDENCE_DIR=(?:\"\")?\s*$", script)
    assert re.search(
        r"(?s)--evidence-dir\).*?EVIDENCE_DIR=\"\$2\".*?shift\s+2",
        script,
    )
    assert re.search(
        r"(?s)\[\[\s+-z\s+\"\$EVIDENCE_DIR\"\s+\]\].{0,240}"
        r"(?:die|exit)\s+64",
        script,
    )


def test_task8_probe_retains_success_evidence_outside_cleanup_scratch() -> None:
    script = _shell_probe()
    cleanup = _shell_function(script, "cleanup")

    assert not re.search(r"rm\s+-rf[^\n]*(?:EVIDENCE_DIR|evidence)", cleanup)
    assert re.search(
        r"(?m)^(?:EVIDENCE_)?MANIFEST_FILE=\"\$EVIDENCE_DIR/[^\"]+\"$",
        script,
    )
    assert 'TEMP_DIR="$EVIDENCE_DIR"' not in script

    success = script.rfind("passed with zero skip")
    assert success >= 0
    before_success = script[:success]
    assert re.search(
        r"(?:>|tee\s+)(?:\s*)\"\$(?:EVIDENCE_)?MANIFEST_FILE\"",
        before_success,
    )
    assert re.search(
        r"\[\[\s+-s\s+\"\$(?:EVIDENCE_)?MANIFEST_FILE\"\s+\]\]",
        before_success,
    )


def test_task8_agent_url_is_bound_to_the_actual_compose_target() -> None:
    script = _shell_probe()
    flattened = re.sub(r"\\\n\s*", " ", script)
    compose_target = re.search(
        r"\bport\s+[\"']?langgraph-api[\"']?\s+[\"']?8000[\"']?",
        flattened,
    )

    assert compose_target is not None, (
        "probe must discover the published langgraph-api:8000 Compose target"
    )
    assert "${TASK8_AGENT_URL:-" not in script
    assert 'export TASK8_AGENT_URL="$AGENT_URL"' in script
    assert compose_target.start() < flattened.index(
        'export TASK8_AGENT_URL="$AGENT_URL"'
    )


def test_task8_restart_proves_identity_unavailability_and_recovery() -> None:
    script = _shell_probe()
    before = _first_index(script, "generation_before=", "container_id_before=")
    restart = _first_index(script, "restart langgraph-api", "stop langgraph-api")
    unavailable = _first_index(
        script,
        "target_unavailable=1",
        "agent_unavailable=1",
    )
    recovered = _first_index(
        script,
        "target_recovered=1",
        "agent_recovered=1",
        "product_recovered=1",
    )
    after = _first_index(script, "generation_after=", "container_id_after=")

    assert before < restart < unavailable < recovered
    assert restart < after
    assert re.search(r"!\s*curl\b", script[restart:unavailable])

    restart_receipt = script[_first_index(script, "jq -n", "python -") :]
    assert re.search(r"\b(?:generation|container_id)_before\b", restart_receipt)
    assert re.search(r"\b(?:generation|container_id)_after\b", restart_receipt)
    assert "target_unavailable" in restart_receipt
    assert "target_recovered" in restart_receipt


def test_task8_live_junit_reports_reject_skip_error_and_empty_collection() -> None:
    script = _shell_probe()
    junit_guard = _shell_function(script, "assert_junit_has_no_skip_or_error")

    assert 'root.iter("testcase")' in junit_guard
    assert "collected no tests" in junit_guard
    for invalid_outcome in ("failure", "error", "skipped"):
        assert invalid_outcome in junit_guard
    for report in ("CONTRACT_JUNIT", "PREPARE_JUNIT", "VERIFY_JUNIT"):
        assert f'assert_junit_has_no_skip_or_error "${report}"' in script


def test_task8_expected_red_is_an_explicit_capability_gap_with_zero_skip() -> None:
    script = _shell_probe()
    expected_red_guard = _shell_function(script, "assert_expected_contract_red")

    assert "CAPABILITY GAP [" in expected_red_guard
    assert "skipped" in expected_red_guard
    assert "errors" in expected_red_guard
    assert re.search(r"(?m)^if\s+[^:]*\bskipped\b", expected_red_guard)
    assert re.search(
        r"(?:search|match|fullmatch)\(detail\)|CAPABILITY GAP \[.*not in detail",
        expected_red_guard,
    ), "every accepted expected RED must match the explicit CAPABILITY GAP marker"


def test_task8_expected_red_cannot_succeed_before_all_live_proofs() -> None:
    script = _shell_probe()
    expected_mode = script.index('if [[ "$EXPECT_CONTRACT_FAILURE" == "1" ]]')
    live_proofs = (
        script.index('node "$NODE_PROBE"', expected_mode),
        script.index("LICENSED_AGENT_SERVER_PROOF_PHASE=prepare", expected_mode),
        _first_index(
            script[expected_mode:], "restart langgraph-api", "stop langgraph-api"
        )
        + expected_mode,
        script.index("LICENSED_AGENT_SERVER_PROOF_PHASE=verify", expected_mode),
        script.index("VERIFY_JUNIT", expected_mode),
    )
    final_live_proof = max(live_proofs)
    early_expected_path = script[expected_mode:final_live_proof]

    assert "exit 0" not in early_expected_path
    assert "return 0" not in early_expected_path

    contract_failure_guard = re.search(
        r"(?m)^if\s+(?P<condition>[^\n]*contract_status\s*!=\s*0[^\n]*)",
        script[expected_mode : live_proofs[0]],
    )
    assert contract_failure_guard is not None
    expected_branch = script[
        expected_mode : contract_failure_guard.start() + expected_mode
    ]
    assert "EXPECT_CONTRACT_FAILURE" in contract_failure_guard.group(
        "condition"
    ) or re.search(r"(?m)^\s*contract_status=0\s*$", expected_branch), (
        "the accepted contract RED must continue into the live proof sequence"
    )


def test_task8_evidence_manifest_binds_runtime_inputs_and_artifact_hashes() -> None:
    script = _shell_probe()
    lower_script = script.lower()

    for artifact_name in (
        "evidence-manifest",
        "receipt",
        "before",
        "after",
        "openapi",
        "version",
        "contract.log",
        "node.log",
        "prepare.log",
        "verify.log",
    ):
        assert artifact_name in lower_script, (
            f"missing retained {artifact_name} evidence"
        )

    for manifest_field in (
        "candidate_sha",
        "image_digest",
        "receipt_sha256",
        "before_sha256",
        "after_sha256",
        "openapi_sha256",
        "version_sha256",
        "contract_log_sha256",
        "node_log_sha256",
        "prepare_log_sha256",
        "verify_log_sha256",
    ):
        assert re.search(rf"\b{manifest_field}\b", lower_script), (
            f"evidence manifest must bind {manifest_field}"
        )

    assert re.search(
        r"git\s+(?:rev-parse\s+--verify|cat-file\s+-e)\b|--candidate-sha\b",
        script,
    )
    assert re.search(r"docker\s+(?:image\s+)?inspect\b", script)
    assert re.search(r"(?:sha256sum|shasum\s+-a\s+256)\b", script)


def test_task8_live_proof_includes_product_command_admission() -> None:
    selectors = _pytest_selectors(_shell_probe())

    assert any(
        "live" in selector
        and "product" in selector
        and re.search(r"admi(?:ssion|tted)", selector)
        for selector in selectors
    ), "probe must select an explicit live Product admission test"


def test_task8_live_proof_includes_server_effective_sync_and_exit_durability() -> None:
    selectors = _pytest_selectors(_shell_probe())
    effective_durability = {
        selector
        for selector in selectors
        if "server" in selector and "effective" in selector and "durab" in selector
    }

    combined = " ".join(sorted(effective_durability))
    assert effective_durability, (
        "probe must select live server-effective durability tests, not only SDK "
        "serialization contracts"
    )
    assert "sync" in combined
    assert "exit" in combined


def test_task8_probe_uses_the_licensed_multi_interrupt_fixture_without_env_sourcing() -> (
    None
):
    script = _shell_probe()
    verifier = IMAGE_VERIFIER.read_text(encoding="utf-8")

    assert (
        'LANGGRAPH_CONFIG_FILE="$BACKEND_DIR/langgraph.multi-interrupt.json"' in script
    )
    assert "LICENSED_AGENT_SERVER_PROOF_PHASE=prepare" in script
    assert "LICENSED_AGENT_SERVER_PROOF_PHASE=verify" in script
    assert "--allow-multi-interrupt-fixture" in verifier
    assert "TASK8_ALLOW_MULTI_INTERRUPT_FIXTURE" in verifier
    assert "source backend/.env" not in script
    assert 'source "$BACKEND_DIR/.env"' not in script


def test_task8_node_probe_uses_the_official_sdk_protocol_surface() -> None:
    script = NODE_PROBE.read_text(encoding="utf-8")

    assert 'frontendRequire("@langchain/langgraph-sdk")' in script
    assert "new Client(" in script
    assert "new ProtocolSseTransportAdapter(" in script
    assert "stream.run.start(" in script
    assert "input.respond(" in script
    assert "openEventStream(" in script
    assert "state.fork(" in script
    assert "fetch(`${apiUrl}/threads/" not in script
