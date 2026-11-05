# LabProof documentation and command index

LabProof is a standalone Python package for synthetic evidence replay and
bounded local synthetic authorization experiments. It does not assess arbitrary
repositories, URLs or commands. The current change is a **versioned foundation**,
not a real Hypothesis/ASan/proptest/fast-check capability release.

## Start here

- [Architecture and trust boundaries](ARCHITECTURE.md)
- [User guide and standalone commands](USER-GUIDE.md)
- [Development and extension gates](DEVELOPMENT.md)
- [Operations and troubleshooting](OPERATIONS.md)
- [Third-party notices and licensing scope](THIRD-PARTY-NOTICES.md)

- [Package overview, existing setup and containment workflow](../README.md)
- [V2 schema, identity, accounting and next real-tool gates](V2-CONTRACT.md)
- [Inference boundary and blocked live construction](INFERENCE.md)
- [Generated codec requests, concrete replay and control interpretation](CODEC-CONTRACT.md)
- [Tool matrix: language packs, operations and acceptance gates](TOOL_MATRIX.md)
- [Retained real container runs](EVIDENCE.md)
- [Threat model](THREAT_MODEL.md) and [evaluation protocol](EVALUATION-PROTOCOL.md)
- [Artifact contract](ARTIFACT-CONTRACT.md)

Python 3.12+ is required. Runtime has no Python package dependencies. Source
testing needs the already-declared pytest extra. The historical foundation milestone performed no
package installation or Docker/image modification. An older installed wheel will not expose the newer commands;
use a current install or the explicit source invocation below.

### Offline source quickstart

From the repository root, Windows PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m labproof demo --output labproof-demo
python -m labproof verify-artifacts labproof-demo
python -m labproof export-viewer labproof-demo --output labproof-viewer.json
python -m labproof experiment-plan --pack python | Out-File -Encoding ascii python-plan.json
python -m labproof experiments --plan python-plan.json --output labproof-v2-blocked
python -m labproof verify-artifacts labproof-v2-blocked
python -m labproof export-viewer labproof-v2-blocked --output labproof-v2-viewer.json
Remove-Item Env:PYTHONPATH
```

POSIX shell, from the repository root:

```sh
export PYTHONPATH="$PWD/src"
python -m labproof demo --output labproof-demo
python -m labproof verify-artifacts labproof-demo
python -m labproof export-viewer labproof-demo --output labproof-viewer.json
python -m labproof experiment-plan --pack python > python-plan.json
python -m labproof experiments --plan python-plan.json --output labproof-v2-blocked
python -m labproof verify-artifacts labproof-v2-blocked
python -m labproof export-viewer labproof-v2-blocked --output labproof-v2-viewer.json
unset PYTHONPATH
```

These are offline commands. `experiments` and its blocked-run verification exit
**2 by design** until separate v2 provisioning is reviewed and supplied. Export
of a valid blocked run exits 0 and preserves its status. PowerShell/POSIX syntax
is supplied; the recorded smoke used Git Bash on Windows with the existing
Python environment and an explicit isolated source path.

For isolated/optimized source verification (replace the absolute source path):

```sh
python -I -O -c 'import sys; sys.path.insert(0, "/absolute/path/labproof/src"); from labproof.cli import main; raise SystemExit(main())' verify-artifacts labproof-demo
```

An installed current release instead uses `python -I -O -m labproof ...` without
source path setup. Fresh installed-wheel acceptance is a separate release gate;
source smoke is not represented as an installed-wheel test.

## Actual CLI reference

| Command | Behavior / gates |
| --- | --- |
| `demo --output NEW_DIR [--max-actions 0..36]` | Canned offline replay; smaller budget retains incomplete artifacts. |
| `verify-artifacts DIRECTORY` | Pure offline verification of replay, local v1, or local v2. Never executes fixtures. |
| `export-viewer DIRECTORY [DIRECTORY ...] --output NEW_FILE` | Verify 1–32 own runs, reject duplicate run IDs, write one exact viewer envelope up to 5 MiB. Existing files are never overwritten. Output must be outside run directories. |
| `experiment-plan --pack python\|typescript\|c\|rust` | Print a six-step v2 default plan (alpha/beta/gamma observations and exact fresh replays). No execution or provisioning. |
| `experiments --plan FILE --output NEW_DIR` | Validate a <=64 KiB plan, require reviewed local v2 provisioning, earn containment acceptance, then execute bounded existing adapters. Currently unprovisioned and therefore blocked. |
| `assess --mode local --pack PACK --output NEW_DIR` | Unchanged legacy v1 local behavior; requires existing reviewed provisioning and live containment acceptance. |
| `compare-experiments BEFORE AFTER --output NEW_FILE` | Snapshot and verify fixed-v2 runs, bind exact bytes, report changed categories and explicit not-comparable cases; no causal proof. |
| `packs` | Catalogue only; declarations are not installed/accepted tool capabilities. |
| `doctor` / `assess` without local mode | Readiness/blocked broader assessment diagnostics, not success. |

Commands emit JSON. Exit codes: **0** successful command or complete valid run;
**2** blocked/incomplete valid assessment or readiness gate; **1** input,
verification, filesystem or policy failure. Argparse usage errors also exit 2.
No command allows imported arbitrary argv, images, executable paths or profiles.

## V1 versus V2

| Area | V1 (preserved) | V2 foundation |
| --- | --- | --- |
| Domain config/report | `local-config-1`, `local-report-1` | `local-config-2`, `local-report-2`, embedded `experiment-plan-2` |
| Manifest/viewer envelope | `1.0` | Still `1.0`; no domain downgrade |
| Work completion | Eight fixed local executions | Up to eight validated steps, profile-required alpha/beta/gamma observations and replays; six-step default |
| Identity | Existing legacy record identity | Full canonical request + phase + step/replay + worker/container/reset + raw/policy/runtime/provenance identities |
| Outcomes | Legacy parser/report rules | Controller completion, child exit, parse status/observation and host verdict are distinct |
| Accounting | Legacy action/output totals | Retained action attempts, returned/unreturned results, replays, completions, elapsed/output totals; unmeasured framework counts remain null |
| Provenance | Existing combined fixture/worker hashes | Separate worker-visible source and host-only oracle; exact retained adapter/worker/image/dependency/compiler/binary metadata |
| Tools | Existing reviewed synthetic adapters | Same adapters only; new tool families remain unimplemented/unaccepted |

Unknown/mixed config/report versions, replay-request substitution, fresh identity
reuse, missing controls, modified outputs/reports and mismatched provisioning
fail verification. Rehashing a modified artifact does not evade domain checks.
Verification checks unsigned consistency, not host authenticity or actual runtime
execution. Smaller plans may be valid to attempt but cannot claim completion
without the profile's controls. Nonzero child exit, parser ambiguity, truncation
or incomplete plans cannot confirm defects.

## Architecture and artifact lifecycle

`cli.py` selects the explicit versioned path. `local_profiles.py` owns immutable
fixed mappings and bounded plans; `local_engine.py` owns trusted provisioning and
runtime orchestration. `sandbox/runtime.py` and `sandbox/policy.py` retain fresh
container lifecycle and containment rules. `local_experiments.py` owns v2
identity/accounting/report derivation; `verify_experiments.py` independently
rechecks retained data using those pure rules. `verify_local.py` dispatches exact
config versions while keeping its legacy derivation. `export_viewer.py` imports
only LabProof and writes verified selected report/event data.

V2 stores `manifest.json`, `config.json`, `acceptance.json`, `attempts.json`,
`executions.json`, `report.json`, `events.jsonl`, `errors.jsonl`, and any retained
`outputs/*.txt` / `evidence/*.json`. An attempted controller call without a
returned worker result is retained in `attempts.json` with null execution ID;
it counts as an action and elapsed time becomes unknown, not zero. Aggregate
experiment budgets exclude the separately bounded fixed containment checks.
They reserve a full worker wall/cleanup/output ceiling before each attempt.
The current adapters have no generated inputs or measured shrink/rejection
traces; no synthetic counts are inferred for them.

## Unprovisioned-v2 gate and next work

The historical foundation package deliberately did **not** ship
`src/labproof/fixtures/local-provisioning-v2.json`, and the source checkout still
does not install that record automatically. Existing v1 `local-provisioning.json`
cannot satisfy v2. The separate builder now derives reviewed source/oracle,
worker and host-code identities from measured inputs rather than relabeling v1.
Missing provisioning still produces verifiable blocked artifacts without workers.

An installed candidate subsequently passed 32 fresh fixed-v2 executions across
all four language packs, including delta observations/replays and offline
verification; see [the exact acceptance scope](V2-CONTRACT.md#recorded-installed-fixed-v2-acceptance).
Subsequent source fixes invalidate that candidate's host-code identity for new
installations. This is neither fresh acceptance of current source nor acceptance
of any new Hypothesis/sanitizer family.

The [next Hypothesis milestone checklist](V2-CONTRACT.md#next-milestone-real-python-hypothesis-not-implemented)
requires reviewed exact dependency/image pins before acquisition, a real codec
fixture and fixed driver/parser, bounded per-invocation traces, retained concrete
counterexamples/replay links, all controls, fresh reproduction, actual containment
and installed optimized verification. Unregistered source prototypes now exist in
`sandboxes/python/hypothesis_codec.py`, `src/labproof/fixtures/codec/python/` and
`src/labproof/adapters/hypothesis_codec.py`, with pure invented-trace and AST tests
in `tests/test_hypothesis_codec.py`. They have not been provisioned or executed
against real Hypothesis, are not CLI-executable profiles and do not extend the
foundation schemas. Selected-version source review targets Hypothesis 6.142.4;
exact wheel/hash review remains blocked by unavailable PyPI metadata. No current
report or catalogue entry satisfies those runtime gates.

## Tests and evidence

Run source tests from any directory with the intended pytest configuration:

```sh
python -m pytest -q -c /absolute/path/labproof/pyproject.toml /absolute/path/labproof/tests
```

New focused tests are `tests/test_local_experiments.py` and
`tests/test_export_viewer.py`. They include invented/mocked completed v2 data;
these are parser/accounting/verification tests, **not runtime acceptance**.
The real container runs retained in `evidence/` are described in [EVIDENCE.md](EVIDENCE.md)
and re-verify offline with `labproof verify-artifacts`. Do not treat source tests as fresh installed-wheel acceptance.

## Operational limits

Use new output directories/files for every run; failed exports are not truncated
or overwritten. Keep complete artifact directories for offline verification,
not only viewer JSON. Export fewer runs if the 5 MiB envelope limit is exceeded.
Do not run fixture code on the host to work around unavailable Docker. Do not
weaken container limits or use inherited credentials/proxies to bypass a gate.
This project has no newly selected open-source license; the owner must decide
project licensing. No new third-party dependency was added by this milestone.
