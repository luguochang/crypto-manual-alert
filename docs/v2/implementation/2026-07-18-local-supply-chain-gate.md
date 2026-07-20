# 2026-07-18 Local Supply-Chain Gate

## Result

`tools/v2/run_local_supply_chain_gate.sh` completed successfully against the
current working tree. The output was written outside the repository under
`/tmp/crypto-alert-v2-supply-chain-current` and was not treated as a release
artifact.

```text
status: passed
attempted_scans: 4
completed_scans: 4
skipped_scans: 0
source_file_count: 337
python_audited_packages: 119
python_vulnerabilities: 0
frontend_audited_dependencies: 582
frontend_vulnerabilities: 0
python_sbom_components: 119
frontend_sbom_components: 574
source_identity_stable_during_scan: true
```

Both CycloneDX SBOMs and both package-manager audits completed. The gate did
not inherit package-manager credentials and did not publish raw tool stderr.

## Boundary

The source tree is dirty and the proof level is
`local-working-tree-supply-chain`. This evidence does not prove a committed
release candidate, hosted dependency audit, container-image SBOM, signature,
release attestation or production release. V2 remains `PARTIAL`;
`Production Ready: NO`.

