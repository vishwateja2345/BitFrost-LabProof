# Native Bifrost decision proposal: mocked only

`labproof.inference.DecisionAdapter` is an explicit opt-in, single-use decision
proposal boundary. It is **not a live integration or autonomous assessment loop**.
There is no CLI route, worker dispatch, tool runner, evidence writer, or report
promotion. A valid proposal remains subject to all existing execution and
independent evidence gates. The declared registry is not proof a tool works.

## Contract and live blocker

Reviewed November 1, 2026:

- https://docs.getbifrost.ai/integrations/anthropic-sdk/overview.md documents the
  official Python `anthropic.Anthropic` client with native
  `base_url="http://localhost:8080/anthropic"` and an explicitly supplied Bifrost
  virtual key through `api_key`. This is not the OpenAI compatibility API.
- https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_client.py
  was inspected for authentication and headers. Its constructor reads
  `ANTHROPIC_CUSTOM_HEADERS` unconditionally, parses newline-separated headers,
  then merges them as
  `{**parsed, **(default_headers if is_mapping_t(default_headers) else {})}`.
  Therefore `default_headers={}` does **not** suppress arbitrary ambient headers,
  including an inherited `Authorization` or `x-api-key`. Explicit credentials
  alone cannot establish the requested no-inherited-secrets guarantee. The
  source also defaults `webhook_key` from `ANTHROPIC_WEBHOOK_SIGNING_KEY` when
  unspecified. This mutable upstream source is not a reviewed version pin.
- https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_base_client.py
  defaults redirect following to true. A future reviewed client must explicitly
  disable redirects, environment proxies (`trust_env=False`), transport retries
  and SDK retries, use bounded timeouts, and prove that auth/profile/WIF,
  headers, logging, and proxy discovery cannot leak ambient data. Disabling
  HTTP environment proxies does not fix the constructor header merge.

`DecisionAdapter.native(credential=..., model=..., live_opt_in=True)` therefore
**always raises `InferenceBlocked` before importing or constructing the SDK**.
Without `live_opt_in=True` it rejects at the earlier opt-in gate. It never reads
credentials/environment, changes the environment, starts a subprocess, or makes
a network call. There is no fallback implementation or raw HTTP path. The only
SDK import is type-checking-only; no optional dependency should be added until
there is an enabled, reviewed construction path. Future dependency/version
selection must be reviewed then rather than installing an unneeded SDK now.

Bifrost documents provider-prefixed routing, but this adapter deliberately accepts
only explicit native `claude-*` model IDs and has no default model. Gateway/model
availability, tool schema support, timeout behavior, redirects, usage fidelity,
and refusal semantics have **not** been tested against a running Bifrost server.
No credentials were read and no live inference calls were made in this work.

## Mocked API

Construct with `injected_client=<trusted SDK-like test double>`, an explicit
`model`, one to sixteen exact `allowed_requests`, `mock_opt_in=True`, and
`reviewed_synthetic=True`. Requests must already pass `REGISTRY.validate_operation`.
Only these structural catalogue requests are sent: no source files, evidence,
free-form prompts, paths, URLs, commands, provider errors, or secret material are
accepted as metadata. The review flag is caller attestation, not content scanning
or an independent review certificate. Catalogue variants reveal no oracle labels.

Call `propose()` once. Its `Decision` contains a status, an optional immutable
`OperationRequest`, usage, `mode="mocked"`, and an attempt count. All accepted
proposals are validated a second time against the fixed registry and the exact
allowed request subset. Tool schema constraints and prompt instructions are not
relied upon for this authorization boundary.

Limits and stop behavior:

- One attempt and one turn per instance, consumed before client configuration or
  request, including failures. A second call is rejected. No retries, resumption,
  fallback models, or rerouting.
- The SDK-shaped invocation uses `with_options(max_retries=0, timeout=10.0)`,
  `max_tokens=512`, non-streaming, and automatic tool choice with parallel tool
  use disabled. More than one returned proposal is rejected regardless.
- Input metadata is capped at 16 KiB. Missing/malformed/negative/boolean usage
  counters remain `None` (unknown), never synthesized zero. Cache counters are
  retained separately; token counts are not represented as measured dollar cost.
- `refusal` and `max_tokens` stop without accepting even a valid tool call.
  Unknown stops, unknown/server content blocks, malformed responses, unsolicited
  operations, or extra fields are rejected. An `end_turn` without tools abstains.
- Full returned SDK `response.content`, including signed/redacted thinking, is
  appended unchanged to the internal transcript; callers receive detached
  copies. No earlier message is rewritten, and no tool result is invented.
- Request failures return a generic `request_error` with unknown usage and no
  exception text. This intentionally collapses error categories because every
  failure terminates without retries; it is not diagnostic provider telemetry.

The injected client is a **trusted test seam, not an isolation boundary**. An
arbitrary Python object can ignore timeouts/retries or execute code; do not inject
a live client as a workaround. The 10-second value is an SDK request timeout, not
a proven total wall-clock deadline. No live redirect/proxy guarantees are claimed
for injection; live construction is blocked precisely so those guarantees are
not silently assumed. Creating fresh instances is not a global spend budget.

## Offline tests

From the repository root:

```sh
python -m pytest -q tests/test_inference.py
```

Tests use SDK-shaped objects and mocks only: accepted and invalid requests,
wrong tool names, narrow subset enforcement, refusal, truncation, abstention,
multiple tools/unsupported stops, complete content preservation, usage unknowns,
failed attempt accounting, explicit opt-ins, input/model bounds, and the
fail-closed live construction gate. These establish application contract
behavior, not official SDK serialization compatibility, live Bifrost behavior,
model selection quality, containment, or autonomous effectiveness.
