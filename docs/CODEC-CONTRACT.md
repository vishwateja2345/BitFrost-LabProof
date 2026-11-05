# Generated codec inputs and controlled reproduction

Status: implemented pure contracts, launch recipes and interpretation with unit
tests. **Not yet a runtime-accepted Hypothesis integration.** The worker remains
outside the legacy fixed-v2 registry. Exact dependency acquisition is blocked by
PyPI DNS resolution; no fabricated wheel hashes or replacement host execution.

## Request and replay identity

`codec_profiles.py` defines `codec-request-1` for
`python-hypothesis-codec-1`. Fields are exactly schema_version, profile_id,
variant, property, seed, cases and replay. Variants are alpha/beta/gamma/delta;
properties are roundtrip/boundary/malformed; seed 0–65535 and cases 1–16 are
integers (not booleans). No paths, commands, model-selected flags or images.

Generation has replay=null. Malformed-frame replay instead carries:

- source_request_sha256: canonical original generation request;
- source_raw_sha256: exact retained worker output bytes;
- example_id: a generated counterexample, never a functional-control example;
- input_hex: bounded concrete malformed frame;
- input_sha256: digest of decoded input bytes.

`make_replay` reparses the source raw output, requires functioning controls and a
host-derived counterexample, then selects an actual generated example.
`validate_replay_source` rederives this request. Seed, case count and property
remain bound to the original. A replay cannot reference another replay. Changing
the variant is allowed only to apply the same input to the reviewed control twins.
The `launch_plan` helper supplies fixed Python/worker argv with a caller-supplied
trusted image ID; creating that recipe is not permission or runtime acceptance.

Legacy `experiment-plan-2` remains unchanged: its replay requests must still be
identical to the original fixed request. Codec requests cannot enter that path.

## Budgets and controls

`codec_experiments.py` reserves actions, target invocations, time and output for
the whole mandatory replay batch before execution. Each prospective worker
reserves the hard 128-call ceiling, including controls and framework rechecks;
max_examples alone is not an invocation budget. Reservations use integer seconds
rounded upward and do not mutate supplied accounting on failure.

`reproduction_batch` applies one selected input to four fresh workers.
`interpret_reproduction` reparses raw bytes, checks source links and distinct
execution/reset identities, and requires one shared counterexample reference.
The narrow successful interpretation is `controlled_reproduction`:

- original alpha reproduces the counterexample;
- corrected beta and normal gamma satisfy the property;
- ambiguous delta stays inconclusive.

Missing/unsafe workers, nonzero exits, timeout/truncation, failed cleanup,
nonreproduction, invalid controls or changed input links cannot promote a result.
An unsafe worker has replay outcome `unavailable`, not an observed `inconclusive`
control. All four workers must return safely parsed observations with completed
or counterexample status; tool errors and invocation-budget exhaustion cannot
substitute for delta's intentionally ambiguous fixture behavior.
This pure function does **not** establish that IDs are authentic or containment
passed. An accepted runtime caller and verifier must supply those bindings before
this observation can enter an end-to-end report. Shared-oracle agreement is not
independent confirmation, and no result establishes production exploitability.

## Remaining integration gates

Review exact Hypothesis/transitive wheel locks, build the fixed codec image,
bind separate worker/source/oracle/adapter/dependency identities, implement and
verify the generated-run artifact lifecycle, then perform actual contained
controls and fresh retained-input replay. Keep shrinking and persistent databases
disabled. Only successful installed optimized runtime acceptance may promote
capability metadata. AST/parser/mock tests are not that evidence.
