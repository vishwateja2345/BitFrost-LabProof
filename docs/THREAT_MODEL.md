# Threat model and operational boundaries

## Replay and local modes

LabProof replay reads frozen observations. Its separate local mode executes only reviewed purpose-built language fixtures after containment acceptance. The viewer is read-only and cannot start tools. No API keys are required for replay, local runs or verification; only the opt-in remediation brief uses credentials (below). Replay remains visibly labelled and cannot establish live model quality or isolation. Real local runs likewise do not establish model/retrieval quality.

## Untrusted inputs

Imported JSON, evidence text, report fields, URLs, paths, and source excerpts are data, never executable instructions. Runtime validation bounds input sizes and validates schema versions, IDs and references. Evidence is displayed as escaped text. An unsigned hash manifest is only a consistency check: a party can rewrite both data and hashes.

Artifact verification must reject traversal, absolute/drive paths, symlinks/reparse points, unknown versions, missing files, altered bytes, dangling evidence IDs, and incomplete event sequences. Error and inconclusive outcomes must not become clean security reports or supported claims.

## Local assessment boundary

The trusted Linux controller alone has access to the fixed Docker socket. Workers run non-root with network none, read-only roots, no host mounts, dropped capabilities, no-new-privileges, and bounded memory/PIDs/CPU/time/output/tmpfs. Only fixed reviewed operation IDs, image IDs and argv are executable. Imported reports cannot authorize execution. Runtime acceptance checks actual policy and canaries before fixtures, and owned-container removal is followed by an absence check. Cleanup failure revokes the session.

Rust explicitly permits executable bounded `/output` for Cargo artifacts; its scratch and temporary mounts remain noexec. Evaluator labels are excluded from worker COPY inputs. Provider secrets never enter workers. The root controller/Docker daemon, installed package and reviewed provisioning are trusted; unsigned retained artifacts are not proof of their authenticity. WSL by itself is not containment, and canary success is not a container-escape guarantee.

Only purpose-built local fixtures are authorized. HTTP service/broker experiments and arbitrary destinations remain unavailable. No host-native fixture fallback, arbitrary commands/targets, generated-code execution, destructive operations, or Windows feature/security changes are in scope. Image builds and dependency acquisition are separate authorized provisioning, not worker-request capabilities.

## External inference and retrieval gate

LabProof's default commands make no model, network or search calls: installation, the offline demo, the planner, local experiments, `verify-artifacts` and `verify-brief` never need credentials. The `inference.py` proposal boundary is mock-tested only and its live constructor is blocked (see [INFERENCE.md](INFERENCE.md)).

The one outbound path is `brief --live --confirm-outbound` ([BRIEF.md](BRIEF.md)). Its boundary:

- **What is sent.** Fixed catalogue queries to Tavily, and a fixed prompt, a fixed class description and public excerpts to the Bifrost gateway. Raw lab evidence, response bodies, run paths and IDs, finding IDs and credentials stay local; a credential travels only in a request header and is never written to a record.
- **Untrusted provider text.** Search excerpts and model replies are data. A prompt injection inside an excerpt can at worst change the wording of a recommendation, because the findings, queries, domains and severities are decided by the host, and a recommendation survives only if each quotation occurs verbatim in a retained excerpt. Rejected proposals are kept as a digest and a reason, never as text. Advice text is plain text without links or markup, the page is escaped and static (`default-src 'none'`, no script), and source URLs are restricted to the allow-listed domains and RFC 3986 characters.
- **Transport.** No redirects, no environment proxies, no client-side retries, no credential discovery, bounded request and response sizes and per-call timeouts. Remote gateways must use HTTPS; plain HTTP is accepted only for loopback. Provider error bodies are never echoed: a failure records an HTTP status and, for Bifrost, a documented refusal type. A reply that reflects the credential is discarded.
- **Spend.** One search and one model call per confirmed class, `temperature` 0 and a token ceiling. Budgets, rate limits and failover belong to the gateway; a refusal is recorded and never retried by changing wording or routing. The output directory is checked before the first call.
- **What it does not establish.** A verbatim quotation is not proof that the advice follows from the source. Digests are unsigned and cannot authenticate a web page or a model. A small local model may yield no verified advice at all.

## Residual limitations

Small synthetic fixtures are not representative pentest or fact-checking benchmarks. Source authenticity and completeness require separate review. Python, TypeScript, C and Rust real runs have retained tested-control evidence. These results do not validate additional tools, HTTP egress enforcement, or autonomous effectiveness. See [EVIDENCE.md](EVIDENCE.md) for the retained runs and the failures that were kept.
