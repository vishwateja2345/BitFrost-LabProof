# LabProof language packs and tool matrix

## Scope and evidence status

This document distinguishes realized fixed local operations from the broader **non-executing catalogue**.

- **Historical implementation and evidence:** Replay, immutable pack/request contracts, pinned four-pack worker recipes and fixtures, a fail-closed Docker controller, retained canary acceptance, strict observation parsers, fresh reexecution, host control grading, local artifact verification, and read-only local viewer imports. This is not fresh acceptance of changed source, images or policy.
- **Historical runtime accepted:** `python-invariants` (stdlib unittest observations), `typescript-node-test` (native Node tests, not tsc), `c-gcc` (GCC-compiled behavior), and `rust-cargo-test` (offline/locked Cargo), all for the **same fixed synthetic authorization family**. Each retained completed run has 8 observations and 1 confirmed, 2 rejected, 1 inconclusive synthetic comparisons. See [EVIDENCE.md](EVIDENCE.md) and `evidence/four-pack-provisioning.json`. These remain the only historically accepted runtime operations.
- **Preserved failures:** The first two C attempts stopped at environment acceptance before fixtures. Corrected public fingerprint whitespace validation and a matching installed wheel allowed `evidence/local-c-03` to complete. A GCC worker is not Clang or sanitizer integration.
- **Parser/source only:** `python-ast` produces structural static observations; the current local CLI selects invariants, not AST. The Hypothesis codec driver, fixtures and pure parser exist but are **unregistered, unprovisioned and unaccepted**. Pure planning source does not dispatch an adaptive worker loop. Static signals alone never confirm.
- **Fixed-v2 accepted candidate, not current-source acceptance:** `evidence/fixed-v2-runtime-01/runtime-acceptance.json` records `accepted_fixed_v2_only` at `/opt/labproof-v2-accept-01/lib/python3.13/site-packages/labproof`: 8 completed verified executions each for Python/TypeScript/C/Rust (32 total), with alpha confirmed, beta rejected, gamma rejected, delta inconclusive. Build records (`evidence/v2-provisioning-01`) supersede the earlier in-progress build status. The coordinator reports an empty post-acceptance `labproof-` Docker inventory, a point-in-time cleanup result. The earlier blocked foundation report (retained locally at `labproof/evidence/foundation-smoke/v2-blocked/report.json`) remains preserved; mock completions remain separate.
- **Current-source installation remains gated:** The accepted fixed-v2 candidate is a dated immutable source revision. Subsequent source fixes changed the package; provisioning hashes all non-fixture `.py` files, so the retained provisioning identity cannot accept a new installation of changed source. Matching reviewed provisioning and fresh runtime/containment acceptance are required. This is not Hypothesis/sanitizer or catalogue promotion.
- **New tested-source checkpoint, not runtime acceptance:** [codec_profiles.py](../src/labproof/codec_profiles.py) binds concrete replay, [codec_experiments.py](../src/labproof/codec_experiments.py) handles pure control interpretation/batch budgets, [experiment_journal.py](../src/labproof/experiment_journal.py) persists checkpoints, [provisioning.py](../src/labproof/provisioning.py) and [provision_v2.py](../sandboxes/provision_v2.py) support separate fixed-v2 provisioning, [experiment_comparison.py](../src/labproof/experiment_comparison.py) verifies fixed-v2 snapshots for comparison. These do not accept Hypothesis, adaptive execution or live advisory compatibility; incomplete checkpoints do not authorize resume and advice is not dispatch authority.
- **Declared only / absent:** The other scanner/property operations below are unverified declarations; accepted generated-input replay and adaptive runtime integration remain future gates despite new pure replay/control source. No native-host fallback is permitted.

This document records retained fixed-v2 acceptance; it does not accept subsequently changed current source. The coverage labels used here (historical runtime accepted, implemented blocked, parser/source only, declared only, absent) are distinct from the registry maturity enum below.

Docker Engine was provisioned in existing Debian WSL with explicit user approval. No Windows feature/security changes were made. Actual runtime evidence supersedes the earlier planning-time missing-daemon status.

## Maturity is evidence, not a package list

| State | Required evidence before promotion |
|---|---|
| `declared` | A reviewed operation surface; no installed/working-tool claim. |
| `parser-tested` | Locked tool/version, output parser tests, malformed/truncated/failing-output cases and retained review evidence. |
| `containment-tested` | Parser evidence plus bounded real canaries for the exact runtime/image/policy: filesystem boundaries, secrets/socket absence, denied networking, non-root/capabilities, time/resources/output ceilings, process-tree cleanup and fresh state. |
| `control-validated` | Containment evidence plus defective/corrected comparison and passing legitimate-use control; ambiguous and static-only cases abstain. |
| `evaluation-approved` | Control evidence plus independently reviewed evaluation protocol, held-out labels and measured outcomes. |

The broad built-in registry still represents tools as **`declared`, unprovisioned**. Fixed local execution is a separate, narrower path using trusted installed provisioning, supported operation mappings, and per-session containment acceptance; it does not promote the rest of the catalogue. Reconciling these metadata surfaces remains work. The schema requires versioned review evidence for promotion, but a digest does not authenticate evidence or prove a test ran. Successful canaries establish only tested controls.

## Initial language-tool matrix

Operation IDs are the finite request vocabulary, not installed commands. A reserved fixture ID `<pack>-synthetic-v1` does not mean the corresponding fixture files exist or have been reviewed. Unless explicitly identified as historical below, these operations are **declared only**; `python-ast` and the unregistered Hypothesis codec pilot have **parser/source only** coverage. The historical fixed local mappings are narrower than the broad catalogue.

| Historical fixed operation | Retained evidence | Not established |
|---|---|---|
| `python-invariants` | Python run (`evidence/local-python-01/manifest.json`) | pytest or Hypothesis |
| `typescript-node-test` | TypeScript run (`evidence/local-typescript-01/manifest.json`) | tsc, ESLint or fast-check |
| `c-gcc` | C run (`evidence/local-c-03/manifest.json`) | Clang, ASan or UBSan |
| `rust-cargo-test` | Rust run (`evidence/local-rust-01/manifest.json`) | Cargo check, Clippy or proptest |

All four historical rows cover fixed authorization fixtures only. The separately retained fixed-v2 candidate accepts those same four operations at its immutable revision, not any new fixture family or subsequently changed source.

| Pack | Declared tools and exact operation IDs | Intended use and limits | Acceptance beyond containment |
|---|---|---|---|
| Python | AST inventory `python-ast`; Ruff `python-ruff`; Bandit `python-bandit` | Static inventory/signals, not proof of a vulnerability. | Parser fixtures and source-span mapping; independent behavior check and controls. |
| Python | stdlib invariant driver `python-invariants`; pytest `python-pytest`; Hypothesis `python-hypothesis`; coverage `python-coverage` | Distinct stdlib invariant checks versus pytest (never masquerading as unittest), bounded properties, exercised-code measurement. Coverage does not establish safety. | Locked dependencies/configuration, bounded seeds/cases, defective/corrected/normal comparison and ambiguous abstention. |
| TypeScript/JavaScript | TypeScript `typescript-tsc`; ESLint `typescript-eslint` | Intended fixed `tsc --noEmit` and local lint configuration; no runtime package acquisition. | Parser tests and independently checked behavior; tool/parse failure remains inconclusive. |
| TypeScript/JavaScript | Node test runner `typescript-node-test`; fast-check `typescript-fast-check` | Fixed contained local tests and bounded properties. No `npx`, arbitrary test path or lifecycle installation. | Locked local dependencies, deterministic seeds/cases and four-variant control cases. |
| C | Clang `c-clang`; clang-tidy `c-clang-tidy` | Compiler/static signals with reviewed fixed flags and configuration. | Parser tests and source/toolchain provenance; warnings alone never confirm exploitability. |
| C | ASan `c-asan`; UBSan `c-ubsan` | Bounded deterministic synthetic inputs; scoped sanitizer observations. | Record fixed flags, source/binary hashes, defective/corrected/normal tests. No payload weaponization. |
| Rust | Cargo check `rust-cargo-check`; Cargo test `rust-cargo-test`; Clippy `rust-clippy` | Intended fixed offline/locked Cargo operations; build scripts/proc macros remain inside containment. | Lock/toolchain hashes, diagnostic parsers, dependency/configuration review and controls. |
| Rust | proptest `rust-proptest` | Bounded deterministic synthetic properties. | Reproducible failing invariant, corrected/normal control, ambiguity handling. |

The broad registry's `version=None` and missing digests intentionally make `require_execution()` fail closed. Actual fixed local image/fixture/worker identities reside in reviewed installed provisioning and retained run configuration, not placeholder registry digests. Python/TypeScript real runs preceded compiled-pack expansion.

### Approved advanced sequence — not runtime acceptance

The priority is **Hypothesis → separate provisioning / generated replay / adaptive-loop milestones → ASan → UBSan → proptest → Clippy → tsc → fast-check**. Separate milestones must not be collapsed into a parser-only completion claim.

| Priority | Required substantive work before acceptance |
|---|---|
| Hypothesis codec | Register a reviewed fixed profile only after versioned parser/evidence contracts, exact dependency pins and bounded boundary/roundtrip/malformed properties are ready. Retain concrete inputs and per-target-call traces, including retries/final rechecks; `max_examples` is not an invocation cap. Start without persistence/shrinking; require corrected/normal/ambiguous controls. |
| Separate provisioning | Review exact image/base, wheel/transitive dependency hashes and offline lock before acquisition/build; bind source separately from host-only oracle and worker/adapter/profile identities. V1 provisioning cannot satisfy v2. Require real image/policy/runtime canaries, fresh state/cleanup, and installed isolated/optimized verification. |
| Generated-input replay | Extend contracts to bind discovered concrete bytes/input hashes to the generating observation, full request and fresh execution/reset. Reproduce the exact input against defect and controls, not merely the same seed or fixed auth request. Missing controls, nonreproduction, truncation or exhausted budgets cannot confirm. |
| Adaptive loop | Integrate the pure selector with only reviewed operations and shared action/time/output/invocation ceilings; retain choices, observations and stop reasons. Keep evaluator labels private. Compare with equal-budget fixed baselines and held-out families before any effectiveness claim. |
| ASan / UBSan | New synthetic memory/undefined-behavior fixtures, exact compiler/flags/source/binary hashes, bounded stderr and strict diagnostics. Separate nonzero sanitizer exits from controller failure; real cgroup compatibility and fresh controls/replay are required. Use explicit nonrecovering UBSan settings; a sanitizer is not exploitability proof. |
| proptest / Clippy | Proptest needs a pinned offline structured property driver with separate successful-case, rejection, shrink and invocation accounting plus concrete replay. Clippy needs a separate diagnostic parser/configuration/profile; static diagnostics cannot confirm behavior. |
| tsc / fast-check | Pin offline `tsc --noEmit` configuration and diagnostic schema independently of Node tests. Fast-check needs bounded deterministic generation, measured calls, concrete replay and controls. No `npx`, package acquisition or lifecycle installs during experiments. |

The codec prototype's source-reviewed Hypothesis 6.142.4 is not an accepted wheel/hash lock. Its parser supports tighter prototype-specific limits than the broad catalogue; neither parser fields nor a catalogue request constitute CLI dispatch authority. `CEX` has no defined local operation/profile/contract meaning and must not be silently expanded or marked implemented.

### Request and runner interface

`REGISTRY.get(pack_id)` returns the frozen `PackManifest`. `REGISTRY.validate_operation(payload)` returns a frozen `OperationRequest` without starting anything. The only JSON request fields are:

```json
{
  "schema_version": "1.0",
  "pack_id": "python",
  "operation_id": "python-hypothesis",
  "fixture_id": "python-synthetic-v1",
  "parameters": {"variant": "alpha", "seed": 0, "cases": 10}
}
```

Every operation requires opaque `variant` in `alpha`, `beta`, `gamma`, `delta`. Defective/corrected/normal/ambiguous classifications are evaluator-only metadata and must not be passed to workers or models as evaluation labels. Hypothesis, fast-check, ASan, UBSan and proptest additionally require `seed` (integer 0–65535) and `cases` (integer 1–100). Other operations accept only `variant`. No free-form command, URL, path, flags, executable, image, resource override or package-manager argument is accepted. Booleans are not numeric limits; floats, huge integers, unknown/duplicate catalogue IDs and unknown fields fail validation. Use the existing bounded `contracts.parse_json()` at a raw JSON boundary so duplicate object keys are rejected before conversion to a dictionary.

Manifest collections and request parameters are immutable tuples; `to_dict()` returns detached JSON-compatible data. Registry construction is a trusted-code surface, **not** an imported-manifest registration API. The manifest digest binds its complete canonical declaration, including resource limits, fixture/tool/adapter identities and maturity. Reserved container roots are `/fixture` (read) and `/scratch`, `/output` (write); these grant no host mounts.

Resource fields are integral and bounded: `wall_seconds` ≤120, `memory_bytes` ≤1 GiB, `cpu_millis` ≤2000 (CPU allocation in thousandths of a core), `pids` ≤128, `scratch_bytes` ≤64 MiB, `output_bytes` ≤2,000,000 and `artifact_count` ≤64. These are declarations, not enforcement; the supervisor must impose them and a total wall deadline independently of cooperative budget checks.

`REGISTRY.require_execution(request, acceptance)` is a **non-executing precondition**. It rejects missing image/fixture/toolchain/tool/adapter identities, insufficient selected-tool maturity, missing acceptance and mismatched pack/image acceptance. All built-in packs fail closed as unprovisioned. `ExecutionAcceptance` is a trusted controller assertion containing pack/image digests, runtime ID, policy digest and canary evidence digest. It is not a signed token, and callers must never accept one from model output or an imported artifact. The runtime must authenticate/review the retained evidence and verify current runtime/policy identity and readiness separately. Passing this pure method is not authorization to install, start a runtime or execute on the host.

`ToolResult` records the immutable request, actual image/fixture identity, tool ID/version, worker/reset IDs, status, exit code, timeout/truncation, bounded diagnostic content references, normalized signal IDs and optional resource observations. Its parser is structural only: a runner must bind it to the registry and actual worker, verify retained bytes/hashes, apply pack-specific limits and diagnostic schemas, and independently grade controls. `completed` means a tool finished, not that a vulnerability was confirmed or that the exit code was zero. Unknown resource measurements remain `None`, not invented zeroes. Diagnostic references use opaque IDs rather than arbitrary filesystem paths. A result cannot itself declare a confirmed verdict.

## What the present tests establish

`tests/test_language_packs.py` tests declaration honesty, exact request fields, enum/integer boundaries, duplicate IDs, deep immutable snapshots, strict digest syntax, resource ceilings, evidence-gated maturity, pack/image acceptance binding and structural result validation. The acceptance test uses explicitly synthetic test identities and does not run a container or scanner. No tool has been promoted by these tests.
