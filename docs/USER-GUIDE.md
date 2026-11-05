# LabProof user guide

## Choose the right path

- **Offline demonstration:** `demo` replays canned synthetic observations. No network, model, or Docker is needed.
- **Read saved evidence:** `verify-artifacts` checks consistency without executing fixtures; `export-viewer` packages selected verified reports/events.
- **V2 foundation:** `experiment-plan` emits a bounded plan. `experiments` currently produces a blocked run because separately reviewed v2 provisioning is absent.
- **Legacy local v1:** `assess --mode local` requires a separately provisioned trusted Linux/Docker environment and fresh containment acceptance to execute workers. Without v1 provisioning it creates a verifiable blocked run with no worker evidence; installing the Python package is not provisioning.

Hypothesis codec source is present but unregistered/unexecuted as an accepted runtime capability. Neither `packs` nor a parser test makes it available.

Paths below use the repository root (`README.md`, `src/`, `pyproject.toml`). No other product is needed.

## Installed release

Use Python 3.12+ in a dedicated environment. Obtain an owner-approved **current** LabProof wheel and validate its release checksum using the release's documented mechanism. This guide does not assert that an existing older wheel includes the v2 CLI. The project metadata currently says `0.1.0`; the filename alone cannot establish which source revision was packaged.

POSIX shell, from a clean working directory outside the extracted release:

```sh
python -m venv /absolute/path/labproof-env
/absolute/path/labproof-env/bin/python -m pip install --no-index --no-deps /absolute/path/release/packages/labproof-0.1.0-py3-none-any.whl
/absolute/path/labproof-env/bin/python -I -m labproof --help
/absolute/path/labproof-env/bin/python -I -m labproof demo --output /absolute/path/work/lp-demo
/absolute/path/labproof-env/bin/python -I -O -m labproof verify-artifacts /absolute/path/work/lp-demo
```

On Windows PowerShell, the environment interpreter is `C:\path\labproof-env\Scripts\python.exe`; invoke it as `& 'C:\path\labproof-env\Scripts\python.exe' -I -m labproof --help`. Wheel and work paths should be absolute. Output parent directories must exist. `--no-index --no-deps` prevents dependency acquisition for this dependency-free runtime; environment creation and installation are operator steps, not actions performed for this documentation.

After selecting that interpreter, the examples below use `python` as shorthand for it. The installed console entry point `labproof` accepts the same arguments, but the explicit interpreter avoids selecting another installation.

## Source invocation without installation

From any clean directory, use the **absolute path to this project's source**:

```sh
python -I -O -c 'import sys; sys.path.insert(0, "/absolute/path/labproof/src"); from labproof.cli import main; raise SystemExit(main())' demo --output /absolute/path/work/lp-source-demo
```

Windows Python should receive a Windows path such as `C:/work/labproof/src`, not a Git Bash `/c/...` path inside the Python string. This isolated form ignores `PYTHONPATH`; alternatively, for a trusted source checkout set `PYTHONPATH` to this package's absolute `src` and use `python -m labproof` **without** `-I`.

All remaining command arguments work with either the installed `python -I -m labproof` prefix or this source prefix.

## Offline workflow and expected end states

Run from a clean work directory with unused output names:

```sh
python -I -m labproof demo --output lp-demo
python -I -O -m labproof verify-artifacts lp-demo
python -I -m labproof export-viewer lp-demo --output lp-viewer.json
python -I -m labproof demo --max-actions 0 --output lp-no-actions
python -I -O -m labproof verify-artifacts lp-no-actions
```

The default demo uses 36 HTTP-shaped **in-memory observations**, not 36 requests. It covers synthetic object authorization, harmless HTML reflection, and verbose error disclosure, with vulnerable/corrected/uncertain variants and normal-use controls in two passes. Both passes read the same frozen snapshot, not independent live evidence. The default fixture derives three confirmed, three rejected, and three inconclusive findings; these are fixture outcomes, not test totals or public vulnerability claims.

`--max-actions` accepts 0–36 and only lowers the hard action ceiling. Both zero-action commands above return **2**; the coherent partial report has `not_tested` findings. Run them separately rather than chaining with `&&` when you want to inspect the expected nonzero result.

| Finding | Meaning |
|---|---|
| `confirmed` | Exact synthetic behavior reproduced with required corrected/normal controls; not arbitrary-target security evidence |
| `rejected` | Tested behavior safe with functioning controls; not a clean bill of security |
| `inconclusive` | Ambiguous, inconsistent, or insufficient controls/completion |
| `not_tested` | Required observations absent |

Harmless reflected markup is not XSS/script execution. Canned traceback/configuration markers are not actual secrets. Public remediation claims remain empty.

## V2 plan and blocked run

POSIX shell:

```sh
python -I -m labproof experiment-plan --pack python > python-plan.json
python -I -m labproof experiments --plan python-plan.json --output lp-v2-blocked
python -I -O -m labproof verify-artifacts lp-v2-blocked
python -I -m labproof export-viewer lp-v2-blocked --output lp-v2-viewer.json
```

For Windows PowerShell, generate the ASCII-only default plan with:

```powershell
python -I -m labproof experiment-plan --pack python | Out-File -Encoding ascii python-plan.json
```

This avoids Windows PowerShell's older UTF-16 redirection default. Do not use ASCII conversion for arbitrary user text.

`experiment-plan` also accepts `typescript`, `c`, and `rust`. It prints a plan; it does not create an output artifact, load Docker, or provision a tool. The default has alpha/beta/gamma observations and exact fresh replays. Initial profiles accept up to eight steps. Plans are at most 64 KiB and cannot introduce commands/images/registrations.

With current absent v2 provisioning, `experiments` and `verify-artifacts` return **2**. Inspect `status: "blocked"`, `acceptance.json`, empty attempted/executed records, and the sanitized error. Export of that **valid blocked run** returns 0 and preserves the blocked status. Do not synthesize provisioning to force a success or use the v1 record as a substitute.

## Legacy local execution

Only in the separately reviewed and provisioned controller environment:

```sh
python -I -m labproof assess --mode local --pack python --output lp-local-v1
python -I -O -m labproof verify-artifacts lp-local-v1
```

Other pack choices are `typescript`, `c`, and `rust`. These use existing narrow fixed adapters, not all tools declared in the catalogue. `assess` without `--mode local` and `doctor` report broader blocked readiness and exit 2; `doctor` does not probe Docker. `packs` lists declarations, exits 0, and is not a runtime acceptance result.

## Experiment planning and synthetic evaluation

These commands run entirely on the host, execute no experiment, and need no Docker, network or model.

```sh
python -I -m labproof plan-next --example > request.json
python -I -m labproof plan-next --input request.json
```

`--example` prints an editable `planning-request-1`: a `model` (hypotheses, a prior summing to 1, and experiments with `cost`, `taintable`, `outcomes` and a likelihood row per hypothesis), the `observations` made so far, a `policy` (`greedy` or `lookahead`, `cost_weight`, `horizon` 1–2, `untrusted_reliability`, `taint_rate`) and a `budget` (`experiments` and a required `cost` key whose value may be null for no cost cap). Each observation is `{experiment_id, outcome, trusted}` with no free text; `trusted` comes from your own registry, and an untrusted observation moves the belief only as far as `untrusted_reliability` allows (0 ignores it). Unknown fields, repeated experiments, impossible outcomes and anything over the bounds are rejected with exit 1.

The result gives the belief, a `decisive`/`inconclusive` label, the feasible experiments ranked by expected information gain, utility and lookahead score, and a recommendation. A recommendation of `null` means nothing fits the remaining budget or is worth its cost; it is not a verdict about the target. A recommendation never launches or authorizes an operation.

```sh
python -I -m labproof evaluate-planner --output planner-eval
python -I -O -m labproof verify-planner-evaluation planner-eval
```

`evaluate-planner` refuses an existing output directory and prints the overall outcome, the three preregistered criteria and a plain-language summary. `analysis.json` holds the arms, paired bootstrap comparisons and the polluted/unpolluted split; `frozen.json` records the two policies chosen on development cases before the test split was scored. `verify-planner-evaluation` recomputes the whole run and returns 0 only when every artifact matches byte for byte; any edit, extra file, missing file or coherently rehashed forgery returns 1. Both commands treat the result as a synthetic benchmark outcome. It is not a vulnerability, tool or model result, and a passing verification does not prove when the rules were fixed.

## Inspection, sharing, and exit codes

Read `manifest.json` first for project, mode, status, and registered paths. Read `report.json` for findings, limitations, provenance, and usage. For v2, follow `completion.missing_controls`, `experiments`, attempt records, evidence IDs, and raw outputs. A controller completion, zero child exit, and recognized parse are separate facts, not synonyms for confirmation.

```sh
python -I -m labproof export-viewer lp-demo lp-v2-blocked --output lp-selected.json
```

Exports accept 1–32 own runs with unique run IDs; the final UTF-8 envelope must fit 5 MiB. Output must be a new file **outside** each run. Export does not truncate, downgrade `local-report-2`, or include a comparison document. A viewer must support that report schema; keep full artifact directories for actual re-verification.

| Exit | Interpretation |
|---|---|
| 0 | Command succeeded, or run/artifact verification is complete; an export can succeed for a blocked run |
| 1 | Input, policy, verification, or filesystem failure |
| 2 | Valid blocked/incomplete/cancelled assessment, readiness gate, or argparse usage error |

Use stdout JSON together with stderr and exit code. Parser/help text is not promised to be JSON. Never equate exit 2 with one universal cause or edit a retained report to make it green.

Command syntax was checked against `src/labproof/cli.py` and current contracts. No installation, build, test, or new CLI execution was performed for this guide.
