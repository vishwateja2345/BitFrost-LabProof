# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's **Report a vulnerability** form (Security tab) rather than a public issue. Include the affected command or file, what you observed, and the smallest input that reproduces it. Expect an acknowledgement, not a service-level guarantee: this is a research prototype.

## What this repository does and does not do

- LabProof is an evidence harness over purpose-built synthetic fixtures. It is not a scanner and not an autonomous pentesting agent. It has no input for a URL, host, port, header, payload or command. Do not point anything in this repository at systems you do not own.
- Every default command (`demo`, `verify-artifacts`, `export-viewer`, `packs`, `doctor`, the planner commands) is offline. They make no network calls, call no model and need no credentials.
- `assess --mode local` runs only fixed, reviewed fixtures through a trusted Linux Docker controller after fresh containment canaries: network none, non-root, read-only root, no host mounts, dropped capabilities, bounded resources, a fresh container per execution and confirmed removal. There is no host-execution fallback. Canary success covers the tested controls, not every possible container escape.
- Imported artifacts and bundles are untrusted data. The viewer displays them as text and never executes them.
- Artifact hashes establish consistency, not authenticity. Nothing here is signed.

## Do not commit secrets

`.env` and `.env.*` are git-ignored. `scripts/audit-repo-readiness.py` is a read-only, heuristic scan for key material and local paths; it is not a guarantee. If you find a credential in the history, revoke it first, then rewrite the history.
