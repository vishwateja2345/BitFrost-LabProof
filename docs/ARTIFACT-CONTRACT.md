# Artifact contract v1 (run envelope)

The LabProof CLI creates a NEW output directory (refuses overwrite) containing `manifest.json`, `report.json`, `events.jsonl`, `errors.jsonl`, and optional evidence files. Manifest matches [run-envelope.schema.json](run-envelope.schema.json). All payload files are registered by relative path, sha256 and byte length. Manifest is an unsigned integrity index, not authentication. Paths must be relative POSIX paths without dot/dotdot, backslash, colon, symlinks or reparse points. File/JSON sizes are bounded.

Events: `{sequence: 1, type: "run_started", run_id: "...", timestamp: "ISO", data: {}}`; sequence consecutive from 1, final event `run_completed` only for completed runs. Domain evidence lives in report.json or registered payload files, and all evidence references must resolve. Errors JSONL may be empty. Runtime verifiers use explicit checks (not assert).

Report common fields: `project_id`, `run_id`, `mode`, `title`, `summary`, `limitations` (string array), `evidence` (array of objects with unique `id`). LabProof adds `findings`; a finding has a unique `id` and `evidence_ids` referencing report evidence.

CLI conventions after installation:
- `python -m labproof demo --output DIR`
- `python -m labproof verify-artifacts DIR`
- `python -m labproof doctor`

Demo commands must use no network or credentials. Mode must be `replay` and limitations explicitly explain synthetic/scripted data. Tests are implementation tests, not validated model benchmarks. The package embeds its own small validation model; the schema file is the interchange specification, not a runtime dependency.
