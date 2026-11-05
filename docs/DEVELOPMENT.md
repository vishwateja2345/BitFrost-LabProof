# LabProof development guide

## Project layout

All source paths here are relative to the repository root: `README.md`, `pyproject.toml`, `src/labproof/`, `tests/`, `sandboxes/`, `docs/`. No other package or schema directory is required at runtime.

Python 3.12+ is required. `pyproject.toml` declares package version `0.1.0`, no runtime dependencies, a `test` extra (`pytest>=8,<10`), and the `labproof = labproof.cli:main` entry point. This package version is distinct from domain strings such as `local-report-2`. Existing wheels must not be assumed current merely because their version matches.

## Development workflow (instructions, not execution claims)

Use an isolated development environment and the intended project path, not whichever package happens to be installed:

```sh
python -m venv /absolute/path/labproof-dev
/absolute/path/labproof-dev/bin/python -m pip install -e '/absolute/path/labproof[test]'
/absolute/path/labproof-dev/bin/python -m pytest -q -c /absolute/path/labproof/pyproject.toml /absolute/path/labproof/tests
```

On Windows use the environment's `Scripts/python.exe`. Editable installation may need network access for missing build/test dependencies; obtain approval and approved artifacts separately. The commands above were **not run for this documentation**. To inspect CLI behavior without installing, use the isolated source prefix in `USER-GUIDE.md`. Do not execute sandbox fixtures directly on the host to substitute for containment.

## Change map

| Concern | Primary files |
|---|---|
| CLI arguments / exit policy | `src/labproof/cli.py` |
| Replay bounds / transport / lifecycle | `policy.py`, `transport.py`, `engine.py` under `src/labproof/` |
| Replay evidence / findings | `evidence.py`, `report.py` |
| Declared operations versus executable profiles | `packs.py`, `local_profiles.py` |
| Provisioning and local lifecycle | `local_engine.py`, `sandbox/runtime.py`, `sandbox/policy.py`, `sandbox/supervisor.py` |
| Existing parsed worker observations | `adapters/observations.py`, `local_report.py` |
| V2 identity, accounting, completion | `local_experiments.py` |
| Offline verification | `contracts.py`, `verify_artifacts.py`, `verify_local.py`, `verify_experiments.py` |
| Own viewer export | `export_viewer.py` |
| Unaccepted codec source | `adapters/hypothesis_codec.py`, project `sandboxes/python/hypothesis_codec.py`, `src/labproof/fixtures/codec/python/` |

Module names without a full prefix in the table are under `src/labproof/`. Read `V2-CONTRACT.md` before changing domain shapes. `ARCHITECTURE.md` describes the module/data/trust flow; `OPERATIONS.md` covers retained evidence handling.

## Extension rules

1. **Keep version dispatch exact.** Preserve replay and local v1 derivation. Add new schemas and deliberate dispatch for changed identity, policy, or parser semantics; do not reinterpret retained v1 fields or silently fall back when v2 validation fails.
2. **Keep executable authority installed and fixed.** An imported plan can select only an existing profile. Never accept plan-supplied argv, images, paths, parsers, graders, or runtime registrations. Adding a catalogue entry is not adding a capability.
3. **Retain full request identity.** Any future supported seed or bounded parameter must participate in request/replay identity. Verify exact observation/replay equality, forward/dangling links, duplicate slots, and cross-step fresh worker/reset identity.
4. **Separate observations from verdicts.** A worker emits bounded raw observations. The trusted parser and host-only oracle derive findings. Unknown output, nonzero exit, timeout, cancellation, truncation, or incomplete controls cannot become confirmation.
5. **Preserve honest accounting.** Count controller attempts even without results. Reserve worst-case worker wall/cleanup/output ceilings before launch. Keep unmeasured invocation/rejection/shrink counts null; do not infer them from configuration. Changed containment controls require actual new acceptance, separate from mocked tests.
6. **Bind provenance accurately.** V2 needs a separate reviewed package-local provisioning record with distinct worker-visible source and host-only oracle digests, adapter/worker and image/dependency/compiler/binary metadata. Unknown/inapplicable values are not invented. Never relabel the legacy combined tree digest.
7. **Verify offline from retained bytes.** Update writer, verifier, raw parser, exact record checks, and deterministic report derivation together. Explicit exceptions must work with `-O`; no security-critical `assert`. Reject mixed types, unsafe paths, unknown fields/versions, tampering even after rehashing, and unsupported completion states.
8. **Keep exports narrow.** Preserve the exact viewer envelope `1.0`; domain v2 stays inside its report. Bound before exclusive output creation, never truncate, and do not imply browser verification of omitted raw files.

```mermaid
flowchart LR
    Contract[Review explicit new contract] --> Source[Fixed profile, parser, driver and oracle]
    Source --> Negative[Parser, identity, budget and tamper tests]
    Negative --> Provision[Separately reviewed pins and provisioning]
    Provision --> Contain[Actual fresh containment acceptance]
    Contain --> Controls[Actual controls and fresh reproduction]
    Controls --> Install[Installed isolated optimized verification]
    Install --> Promote[Only then update capability claims]
```

The arrows are gates, not assertions that work has passed them. V2 remains blocked because separate provisioning is absent.

### Hypothesis boundary

The tree contains a pure codec parser, proposed driver, codec fixtures, and focused tests. These are **source-only, unregistered and unexecuted as an accepted runtime path**; the four existing `EXPERIMENT_PROFILES` still derive from legacy fixed profiles. Do not document the parser's version literal as an acquired/installed dependency pin or describe source controls as observed runtime controls.

The next accepted milestone needs reviewed exact image and dependency wheel/version/hash pins, transitive/offline lock, actual source/oracle/adapter identities, a fixed bounded driver/parser, concrete input and per-invocation/replay traces, independently enforced/countable target-call bounds, and required defective/corrected/normal/ambiguous controls. It also requires fresh concrete counterexample reproduction, actual containment checks, and installed `-I -O` verification. Consult the contract checklist; source existence does not supersede it.

## Verification strategy

Existing focused files include `tests/test_local_experiments.py`, `test_local_profiles.py`, `test_export_viewer.py`, `test_local_artifacts.py`, `test_sandbox_policy.py`, `test_sandbox_runtime.py`, `test_worker_observations.py`, and `test_hypothesis_codec.py`; replay coverage is in `test_labproof.py`. Tests that fabricate completed v2 records exercise derivation, not execution acceptance. Optional external schema or platform symlink checks may depend on local availability/privileges; do not treat a skip as a passed containment gate.

For a retained source artifact, the optimized source verification shape is:

```sh
python -I -O -c 'import sys; sys.path.insert(0, "/absolute/path/labproof/src"); from labproof.cli import main; raise SystemExit(main())' verify-artifacts /absolute/path/run
```

For an approved installed wheel, use its environment interpreter with `-I -O -m labproof verify-artifacts /absolute/path/run`. This is a **separate** gate from source tests. Preserve commands, interpreter/package/source identity, exit codes, fixture status, and limitations with any acceptance evidence. This documentation pass ran no tests/builds/installations and makes no new test-total or runtime-success claim.

## Release review

Check packaged files and commands against the selected source revision; no silent dependence on files outside this repository is permitted. Verify ordinary replay and blocked v2 artifacts in an unrelated clean directory, using the newly installed wheel and isolated optimized Python. Check that blocked-run export preserves status and that unknown/mixed schemas fail. Do not include credentials, host-only material in worker image copy inputs, or unreviewed provisioning. Licensing and third-party acquisition approval remain owner decisions; a documentation update does not grant either.
