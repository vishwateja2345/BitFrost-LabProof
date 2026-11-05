# Retained real container runs

The `evidence/` directory holds the artifacts of real LabProof runs made on the author's machine with Docker Engine in a Debian WSL distribution. Every directory re-verifies offline, without Docker: `python -m labproof verify-artifacts evidence/local-python-01`. Hashes are unsigned: they show that the files are consistent with each other, not that the runs happened as described.

Only purpose-built synthetic fixtures are in scope. No external-target testing and no paid model or search calls were performed. The author authorized project dependencies, Docker Engine in an existing Debian WSL distribution and pinned worker-image provisioning.

Unsigned artifact hashes establish consistency, not authenticity. Reexecution plus host control rules is not a separate human/model audit. Canary results establish tested controls, not immunity to container escapes.

## Real runtime and retained artifacts

Docker Engine 26.1.5 was installed in Debian WSL with a separate Linux controller environment at `/opt/labproof-venv`. The controller alone uses the fixed local Docker socket. Experiments use prebuilt image IDs, network-none non-root workers, read-only roots, no host mounts, dropped capabilities, no-new-privileges, bounded resources/output/time, and fresh containers. Owned-container removal is followed by an absence check.

[`evidence/four-pack-provisioning.json`](../evidence/four-pack-provisioning.json) records actual pinned bases, built image IDs, and fixture/worker tree hashes. Builds used `--network=none --pull=false` after separately authorized base downloads. Evaluator oracle files are excluded from worker-image COPY inputs.

| Retained run | Actual result | Artifact verification |
|---|---|---|
| `evidence/local-python-01` | Completed: 8 observations; 1 confirmed, 2 rejected, 1 inconclusive | Valid, complete |
| `evidence/local-typescript-01` | Completed: 8 observations; 1 confirmed, 2 rejected, 1 inconclusive | Valid, complete |
| `evidence/local-rust-01` | Completed: 8 observations; 1 confirmed, 2 rejected, 1 inconclusive | Valid, complete |
| `evidence/local-c-01` | Blocked at image environment acceptance, before fixture execution | Valid, incomplete |
| `evidence/local-c-02` | Blocked with stale installed validation | Valid, incomplete |
| `evidence/local-c-03` | Completed: 8 observations; 1 confirmed, 2 rejected, 1 inconclusive | Valid, complete; optimized verifier |

Completed packs compare four opaque variants in observation and fresh-container verification phases. Confirmations are scoped synthetic authorization comparisons, not arbitrary software assessments. Actual operations are Python stdlib invariants, native Node tests over erasable TypeScript (not tsc), and Rust `cargo test --offline --locked`. C executes the fixed GCC-compiled synthetic worker; it does not claim Clang/sanitizer coverage.

Actual canaries checked UID/GID 65532, zero capabilities, no-new-privileges, loopback-only interfaces, Docker socket absence, root write denial, fresh state, cgroup limits, timeout/child cleanup, and output truncation/cleanup. Rust additionally checked executable bounded `/output` while `/tmp` and `/scratch` remain noexec. The last completed Docker worker inventory was empty; this is a point-in-time result, not ongoing monitoring.


## Fixed-v2 runtime acceptance

[`evidence/fixed-v2-runtime-01/`](../evidence/fixed-v2-runtime-01) records an installed fixed-v2 candidate: 32 fresh verified executions, eight each for Python, native Node tests, GCC and offline Cargo, with alpha confirmed, beta rejected, gamma rejected and delta inconclusive. It is acceptance of that dated source revision, not of any later change; see [V2-CONTRACT.md](V2-CONTRACT.md#recorded-installed-fixed-v2-acceptance).
