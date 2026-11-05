# Live record: a sourced remediation brief with Bifrost and Tavily

The first real runs of `labproof brief --live`, made on 2026-11-05 (UTC) against the retained Python container run [`../local-python-01`](../local-python-01). Every brief in this directory passes `python -m labproof verify-brief evidence/local-python-01 <directory>`.

## Set-up

| Part | What was used |
|---|---|
| Gateway | Bifrost `maximhq/bifrost:v2.4.0` in Docker on loopback, configured by [`scripts/live-brief/config.json`](../../scripts/live-brief/config.json): an Ollama provider, a `tavily` relay limited to `POST /search`, and one virtual key with a 0.4 budget |
| Model | `ollama/qwen2.5:3b`, CPU only (Ollama in Docker, WSL2 with 4 vCPUs), `temperature` 0, `max_tokens` 700 |
| Search | Tavily `basic`, restricted to `owasp.org` and `cwe.mitre.org`; once direct (`--tavily-key-env`) and once through the Bifrost relay (`--search-relay tavily`) |
| Command | `scripts/live-brief/run.sh` with `CALL_TIMEOUT=180` |

## Outcomes

| Record | Search | Model call | Result |
|---|---|---|---|
| [`direct/`](direct) | Tavily direct, 3 sources, 1 credit | 798 prompt and 128 completion tokens, served by `ollama/qwen2.5:3b` | `sourced`: 1 verified recommendation |
| [`relay/`](relay) | Tavily through the Bifrost relay, 3 sources, 1 credit (the gateway's relay log counted 1 request, cost 0.008) | the same 798 and 128 tokens | `sourced`: 1 verified recommendation |
| [`attempt-1/direct/`](attempt-1/direct) | Tavily direct, 3 sources, 1 credit | the gateway answered HTTP 504: the CPU-only model did not reply within the gateway's 145 s provider timeout while another workload was using the CPU | `model_failed`, recorded and not retried |
| [`attempt-1/relay/`](attempt-1/relay) | Tavily through the relay, 3 sources, 1 credit | a reply arrived (798 and 128 tokens) but its JSON was missing the outer closing brace | `no_verified_advice`: the one proposal was rejected as `reply_not_json` |

The two `attempt-1` records are kept on purpose: they show what the failure paths look like on real services. Their `brief.html` was re-rendered from `brief.json` with the final stylesheet; the page is a pure function of the JSON and `verify-brief` checks it.

## What changed between the attempts

1. The `attempt-1` relay reply showed that `qwen2.5:3b` can leave off the last brace of its JSON.
2. A second attempt that also sent `response_format: {"type": "json_object"}` gave the same two outcomes. A probe then showed why: Ollama honoured the field when called directly, but Bifrost v2.4.0 accepted and ignored it for the Ollama provider (the same prompt returned plain text through the gateway). `--json-mode` therefore stays opt-in. That attempt's briefs are not retained.
3. The host now completes a reply whose only defect is missing closing brackets. It never repairs anything inside a string, never adds content, and every other check (strict shape, link-free text, verbatim quotations) is unchanged.
4. The final `direct` and `relay` runs, with the same model and prompt, were both `sourced`.

## The verified recommendation

Model-generated text, with both quotations checked to occur verbatim in the retained excerpt of the OWASP API Security Top 10 (2023) page `https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization`:

> Implement proper object-level authorization checks in every function that accesses a data source using an ID from the user to ensure that the logged-in user has permissions to perform the requested action on the requested object.

- "Implement a proper authorization mechanism that relies on the user policies and hierarchy."
- "Use the authorization mechanism to check if the logged-in user has access to perform the requested action on the record in every function that uses an input from the client to access a record in the database."

The other two retained sources are `https://owasp.org/API-Security/editions/2023/en/0x11-t10` and `https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html`.

## What this does and does not show

- It shows both integration paths working end to end against the real services: Tavily returning current OWASP pages, a model reached only through a Bifrost virtual key, Bifrost's relay carrying the search, and LabProof keeping only what passes its own checks.
- It does not show that the advice is correct. The quotation check removes invented sources and wording; it is not proof that the sentence follows from the quotes. A small CPU-only model is slow (a cold first call took about a minute in our runs) and not reliable: in the first attempt one of the two runs hit a timeout and the other needed a host-side fix.
- Excerpts are Tavily snippets of OWASP pages, kept with their URLs and dates; the dates are Tavily's estimates. OWASP publishes its material under Creative Commons licenses; check the license on each source page before reusing an excerpt.
- Digests are unsigned: they show the briefs are consistent with the run and the retained excerpts, not that the pages really said so.

## Reproduce

```bash
TAVILY_API_KEY=... CALL_TIMEOUT=180 scripts/live-brief/run.sh
```

See [`docs/BRIEF.md`](../../docs/BRIEF.md) for the set-up and the data boundary. The credentials are never written to a brief, and none is stored in this repository.
