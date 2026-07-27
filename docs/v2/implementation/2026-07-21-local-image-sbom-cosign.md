# Local Image SBOM and Cosign Evidence

## Scope

This slice adds reproducible local evidence for the current dirty-worktree backend
container image. It does not create or attest a release candidate.

## Image SBOM

`tools/v2/run_local_image_supply_chain_gate.py` rebuilds the backend image, binds the
source manifest and CycloneDX root purl to the exact local image ID, invokes Docker Scout
only through `local://<image-id>`, checks source/image stability, excludes every `.env*`
path before reading source bytes, scans retained evidence and emits byte-stable SHA256
receipts.

Fresh evidence:

- `E:\project\study\codex\crypto\container-image-sbom-20260721-06`
- image ID: `sha256:c2935db338c1f4ccaaf66e06ffe5639ddbc0a1f9801813cff8192413555b779e`
- CycloneDX 1.5: 773 components, 2668 dependency entries, 773 purls
- all six listed artifacts: SHA256 verified
- secret and environment-path matches: zero

## Local Cosign Rehearsal

`tools/v2/run_local_cosign_bundle_gate.py` re-verifies the SBOM evidence bundle, uses
official Cosign `v2.4.3` at immutable GHCR digest, signs its full SHA256 list with an
ephemeral local key under `--network none`, verifies the signature offline, rejects a
tampered subject and deletes the private key before publishing evidence.

Fresh evidence:

- `E:\project\study\codex\crypto\container-image-signature-20260721-03`
- all five listed artifacts: SHA256 verified
- independent Cosign verification: `Verified OK`
- private key, tampered subject, secret and staging residue counts: zero

## Boundary

The local image has no immutable registry repo digest. Docker Scout CVE analysis remains
credential-gated. The Cosign proof deliberately disables transparency-log upload and
uses an ephemeral key; it is not protected key custody, keyless OIDC identity, Rekor or
RFC3161 inclusion, registry image signing, signed OCI SBOM/provenance attestation,
operator approval or production release evidence.

V2 remains `PARTIAL`; `Production Ready: NO`.
