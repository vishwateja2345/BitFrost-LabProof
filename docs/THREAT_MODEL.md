# Threat model and operational boundaries

## Replay and local modes

LabProof replay reads frozen observations. Its separate local mode executes only reviewed purpose-built language fixtures after containment acceptance. The viewer is read-only and cannot start tools. No API keys are required. Replay remains visibly labelled and cannot establish live model quality or isolation. Real local runs likewise do not establish model/retrieval quality.

## Untrusted inputs

Imported JSON, evidence text, report fields, URLs, paths, and source excerpts are data, never executable instructions. Runtime validation bounds input sizes and validates schema versions, IDs and references. Evidence is displayed as escaped text. An unsigned hash manifest is only a consistency check: a party can rewrite both data and hashes.

Artifact verification must reject traversal, absolute/drive paths, symlinks/reparse points, unknown versions, missing files, altered bytes, dangling evidence IDs, and incomplete event sequences. Error and inconclusive outcomes must not become clean security reports or supported claims.

## Local assessment boundary

The trusted Linux controller alone has access to the fixed Docker socket. Workers run non-root with network none, read-only roots, no host mounts, dropped capabilities, no-new-privileges, and bounded memory/PIDs/CPU/time/output/tmpfs. Only fixed reviewed operation IDs, image IDs and argv are executable. Imported reports cannot authorize execution. Runtime acceptance checks actual policy and canaries before fixtures, and owned-container removal is followed by an absence check. Cleanup failure revokes the session.

Rust explicitly permits executable bounded `/output` for Cargo artifacts; its scratch and temporary mounts remain noexec. Evaluator labels are excluded from worker COPY inputs. Provider secrets never enter workers. The root controller/Docker daemon, installed package and reviewed provisioning are trusted; unsigned retained artifacts are not proof of their authenticity. WSL by itself is not containment, and canary success is not a container-escape guarantee.

Only purpose-built local fixtures are authorized. HTTP service/broker experiments and arbitrary destinations remain unavailable. No host-native fixture fallback, arbitrary commands/targets, generated-code execution, destructive operations, or Windows feature/security changes are in scope. Image builds and dependency acquisition are separate authorized provisioning, not worker-request capabilities.

## External inference and retrieval gate

LabProof makes no model, network or search calls: installation, the offline demo, the planner and local experiments never need credentials. The `inference.py` proposal boundary is mock-tested only and its live constructor is blocked (see [INFERENCE.md](INFERENCE.md)). Any later model or search call needs explicit credentials configured locally, a spending cap and its own review; secrets are never logged, a refusal is never retried by changing wording or routing, and raw lab evidence, response bodies, identifiers and credentials stay local.

## Residual limitations

Small synthetic fixtures are not representative pentest or fact-checking benchmarks. Source authenticity and completeness require separate review. Python, TypeScript, C and Rust real runs have retained tested-control evidence. These results do not validate additional tools, HTTP egress enforcement, or autonomous effectiveness. See [EVIDENCE.md](EVIDENCE.md) for the retained runs and the failures that were kept.
