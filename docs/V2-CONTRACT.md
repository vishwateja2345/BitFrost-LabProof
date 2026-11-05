# LabProof local v2 contract

> Paths under `evidence/` cited below are retained run artifacts included in this repository.

Status: versioned foundation, not acceptance of any new tool. Legacy replay and
`local-config-1` / `local-report-1` behavior and derivation are unchanged.

## Domain and viewer boundary

The manifest stays `schema_version: "1.0"`, `project_id: "labproof"`, `mode:
"local"`. V2 requires `local-config-2`, `experiment-plan-2`, and
`local-report-2` together; unknown/mixed versions fail closed. Reports retain
`project_id`, `run_id`, `mode`, `status`, `pack_id`, `title`, `summary`,
`limitations`, `provenance`, `public_remediation_claims: []`, `evidence`,
`findings`, and `usage`. New report fields are `plan`, `experiments`, and
`completion`. Evidence entries remain `{id,title,content,artifact_path,record}`.
`experiments` expose per-step request, phase, replay link, execution identity,
controller completion, child exit, parse status, and observation separately.
Findings remain host-derived legacy synthetic authorization findings, never
worker-supplied verdicts. Unknown diagnostics/nonzero exit cannot confirm a flaw.

`export-viewer DIRECTORY [DIRECTORY ...] --output FILE` verifies each own run
without executing it, rejects duplicate run IDs, and exclusively creates UTF-8
JSON of at most 5 MiB (no truncation). Envelope is exactly
`{schema_version:"1.0",generated_at,runs:[{manifest,report,events}],annotations:[],limitations:[...]}`.
The browser must explicitly support `local-report-2`; export does not downgrade
v2 or claim the browser independently verifies omitted raw artifacts.

## Bounded plan and trusted authority

A plan has exactly `schema_version`, `profile_id`, `budgets`, `steps`.
Budgets: `actions`, `wall_seconds`, `output_bytes`. Steps have exactly `id`,
`request` (existing canonical OperationRequest), `phase` (`observation` or
`verification`), `replay_of` (earlier observation step or null). At most 8 steps
for the initial profiles; a smaller plan is valid but cannot complete without
profile-required corrected/normal and fresh replay controls. Each verification
must replay exactly the full request of its earlier observation. Request keys
hash full validated requests and phase, including seed and bounded parameters
when a future reviewed profile supports them. Initial profiles support only the
four existing fixed behavioral operations/fixtures; declared Hypothesis etc.
remain blocked. No plan-specified argv, image, parser, grader or registration.

Each evidence identity hashes step ID, full request/key, phase, replay link,
fresh execution/container/reset identity, image/policy/runtime/provenance
bindings, raw output digest, and parsed observation. Cross-step worker/reset
reuse and canary reuse are forbidden. Same identity aliases within one runtime
result are permitted (the existing runtime uses container ID for all three).

## Execution and accounting

Execution records distinguish controller state (`completed` or `interrupted`),
child return code (nullable), timeout/cancel/truncation/cleanup flags, parsed
observation (nullable) and parse status (`parsed`, `unrecognized`, `unavailable`).
Elapsed time and retained output bytes are aggregated from records. Action
reservations conservatively reserve per-worker wall+cleanup/output limits
before launch. Required replay/control completion is profile-owned, not a
universal eight-execution assertion. V2 accounting exposes actions, parsed
observations, completed steps, replays, target invocations, rejections, shrinks,
elapsed seconds and output bytes. Unmeasured target/framework counts are null,
not inferred from max_examples or a successful exit. Legacy adapters retain
fixed inputs but have no generated-counterexample/shrink instrumentation;
future property drivers require a separately versioned parser/profile extension.

New executions also persist append-only, flushed/fsynced `checkpoints.jsonl`
records before each worker attempt and after returned results. These retain the
plan, accepted configuration, attempt order and execution records if the process
exits before manifest creation. An unfinished journal is diagnostic evidence,
not a completed artifact, permission to resume, or a claim that cleanup succeeded.
For finalized runs the offline verifier rederives every checkpoint. Historical
v2 runs without checkpoints remain readable; checkpoint presence does not
establish authenticated execution.

## Provenance and gates

V2 requires trusted package-local `local-provisioning-2` records, never records
from imported plans. They bind image/base, worker-visible source digest,
host-only oracle digest, worker/adapter digest, dependency-lock digest,
compiler version/flags and binary digest (inapplicable/unknown values null).
Source and oracle are distinct fields; old fixture tree hashes cannot silently
be relabeled as either. Configuration retains the exact provenance record and
its digest. Missing v2 provisioning produces a verifiable blocked run, not a
fallback to v1 provisioning. Changed provisioning always requires new live
session containment acceptance. The separate `sandboxes/provision_v2.py` builder
now emits candidate records; none are automatically installed or runtime-accepted.
Unsigned hashes are internal consistency, not runtime/source authenticity.
Offline verification rederives whole launch-policy sets for the two fixed reviewed
controller identities (Linux and Windows), rather than assuming the reader's OS
was the producer's OS. Mixed-controller policy sets and unreviewed settings fail.
Live execution still binds only to the current controller; offline alternatives
never enable another executable, endpoint, environment or launch command.

### Explicit provisioning builder

Run with an installed matching LabProof package and isolated Python:

```text
python -I /absolute/labproof/sandboxes/provision_v2.py --project /absolute/labproof --pins /absolute/reviewed-pins.json --output /absolute/new-build-record
```

This command builds images and needs authorized access to the existing Docker
controller; it is not an offline installation/verification command. Do not change
socket permissions or fall back to host fixture execution when access fails.
The reviewed input is exactly `{"schema_version":"reviewed-local-bases-1",
"bases":{"python":"python@sha256:<64 lowercase hex characters>"}}` (placeholder,
not an executable pin). Keys may select python/typescript/c/rust; only their
corresponding official digest-pinned base repositories are allowed. Bases must
already exist locally. No tag resolution, pulls or dependency installation.

`src/labproof/provisioning.py` hashes canonical sorted `{path,bytes,sha256}`
inventories. Source covers exactly the fixture files copied by each fixed recipe;
oracle JSON has a separate identity. Adapter identity conservatively covers all
installed non-fixture Python source, including the embedded host grader. Worker
identity covers its fixed Dockerfile/source inputs; Rust's Cargo.lock is also
identified separately. Compiler and binary measurements remain null in this
legacy builder, not invented observations. This does not satisfy the additional
compiler/binary acceptance requirements for future sanitizer adapters.

The builder stages only measured worker/source inputs into a private context;
it does not send the oracle or project tree to Docker. It checks source stability,
uses unique image tags and a new output directory, streams bounded build output,
and retains attempted/failed build records. A successful build is explicitly
`built_not_runtime_accepted`. Candidate provisioning remains outside the package
until a separate trusted installation step. Before a v2 session is created, the
controller recomputes installed source/oracle/host-code identities and rejects
stale or mismatched records. Existing v1 provisioning is untouched.

## Recorded installed fixed-v2 acceptance

`evidence/fixed-v2-runtime-01/runtime-acceptance.json` records an isolated, optimized
installed candidate run: **32 fresh executions**, eight each for Python, native
Node tests, GCC and offline Cargo. Each pack observed and replayed alpha, beta,
gamma and delta with the expected confirmed/rejected/rejected/inconclusive
synthetic authorization results. Each complete artifact set passed offline
verification. A subsequent owned-container inventory was empty.

This accepts only that installed candidate and its exact recorded identities.
The source has since changed; the
conservative host-code digest therefore requires new matching provisioning and
installed acceptance before calling the current source accepted. The earlier
candidate and failure records remain intact. Nothing here accepts Hypothesis,
sanitisers, an adaptive loop, model calls or arbitrary targets.

## Next milestone: real Python Hypothesis (not implemented)

Before acquisition/build: review an exact Python base image digest, exact
Hypothesis wheel/version/hash and transitive wheel/version/hashes, offline lock,
worker/adapter source hashes, codec source hashes and a separate host-only oracle
hash. No dependency version/hash is invented by this foundation. A new fixed
codec profile/parser is required; the old authorization fixture is not a codec.
Disable example database and shrinking, bound seed/input bytes/examples and
rejections; independently cap/count every target call including retries. Retain
concrete bounded inputs and per-invocation/replay links. Budget exhaustion cannot
pass. Exercise boundary/roundtrip/malformed properties, defective/corrected/
normal/ambiguous controls, fresh counterexample reproduction, parser negatives,
actual containment canaries and installed `-I -O` artifact verification. Only
after those gates may capability metadata change. No Docker/image/dependency
changes, installs, or capability promotion are part of this foundation. An
unregistered codec worker/fixture/pure-parser source prototype and invented-trace
tests have been added subsequently; these do not enable a real tool or alter the
foundation schema. Tagged Hypothesis 6.142.4 source review confirms final failure
rechecks happen even with only Phase.generate. Wheel hashes/provisioning review,
actual runtime execution, fresh controls/replay and containment remain outstanding.
