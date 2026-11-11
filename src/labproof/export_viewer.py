"""Export checked run snapshots and optional offline-verified remediation."""
from hashlib import sha256
from pathlib import Path

from .contracts import canonical, check_no_links, parse_json, read_safe, require
from .engine import now, write_new
from .verify_artifacts import verify_artifacts

MAX_VIEWER_BYTES = 5 * 1024 * 1024
MAX_VIEWER_TEXT_UNITS = 200_000
MAX_VIEWER_NODES = 150_000
MAX_VIEWER_DEPTH = 32
LIMITATIONS = [
    "Exported runs passed LabProof's own offline artifact consistency verification.",
    "Unsigned artifacts and hashes do not authenticate sources or prove execution occurred.",
    "The viewer envelope omits raw artifact files; browser inspection is not independent artifact verification.",
    "Incomplete and blocked runs remain incomplete or blocked; no evidence is truncated.",
]


def _check_viewer_limits(bundle):
    pending = [(bundle, 0)]
    visited = 0
    while pending:
        value, depth = pending.pop()
        visited += 1
        require(visited <= MAX_VIEWER_NODES and depth <= MAX_VIEWER_DEPTH,
                "Viewer export is too large or too deeply nested for browser import")
        if isinstance(value, str):
            # The browser counts UTF-16 code units.
            require(len(value.encode("utf-16-le", "surrogatepass")) <= 2 * MAX_VIEWER_TEXT_UNITS,
                    "Viewer export contains a text field over 200,000 UTF-16 code units")
        elif isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)


def export_viewer(directories, output, *, brief_dir=None, expected_manifest=None, expected_brief=None):
    require(type(directories) in (list, tuple) and 1 <= len(directories) <= 32, "Export requires 1–32 own run directories")
    require(expected_manifest is None or len(directories) == 1, "Snapshot export requires one source run")
    output = Path(output).absolute()
    check_no_links(output.parent)
    require(not output.exists(), "Export output already exists")
    runs, seen, remediation = [], set(), None
    require(expected_brief is None or brief_dir is not None, "Approved brief directory required")
    if brief_dir is not None:
        brief_dir = Path(brief_dir).absolute()
        require(output != brief_dir and brief_dir not in output.parents, "Export must be outside the brief directory")
    for directory in directories:
        root = Path(directory).absolute()
        require(output != root and root not in output.parents, "Export must be outside the verified run")
        before = read_safe(root, "manifest.json")
        require(expected_manifest is None or before == expected_manifest, "Manifest changed after export approval")
        manifest = parse_json(before)
        require(isinstance(manifest, dict) and manifest.get("mode") in ("replay", "local"),
                "Viewer export supports replay and local runs")
        verified = verify_artifacts(root, expected_manifest=before)
        manifest_raw = read_safe(root, "manifest.json")
        require(manifest_raw == before, "Manifest changed during export verification")
        require(manifest["run_id"] == verified["run_id"] and manifest["run_id"] not in seen, "Duplicate/changed run identity")
        seen.add(manifest["run_id"])
        entries = {entry["path"]: entry for entry in manifest["artifacts"]}
        selected = {}
        for name in ("report.json", "events.jsonl"):
            raw = read_safe(root, name)
            require(len(raw) == entries[name]["bytes"] and sha256(raw).hexdigest() == entries[name]["sha256"], "Artifact changed during export")
            selected[name] = raw
        events = [parse_json(row) for row in selected["events.jsonl"].splitlines()]
        report = parse_json(selected["report.json"])
        versions = ("1.0",) if manifest["mode"] == "replay" else ("local-report-1", "local-report-2")
        require(report.get("schema_version", "1.0") in versions, "Report version is not supported by the viewer")
        if brief_dir is not None and not runs:
            from .brief import read_verified_brief

            require(verified["complete"] and manifest["mode"] in ("replay", "local"),
                    "A brief needs a completed replay or local run")
            remediation, _ = read_verified_brief(
                brief_dir, manifest, report, sha256(manifest_raw).hexdigest(), entries["report.json"]["sha256"],
                expected_json=expected_brief,
            )
        runs.append({"manifest": manifest, "report": report, "events": events})
        # Bound accumulated output while loading, not only at the eventual write.
        require(len(canonical(runs)) <= MAX_VIEWER_BYTES, "Viewer export exceeds 5 MiB; select fewer runs")
    bundle = {"schema_version": "1.0", "generated_at": now(), "runs": runs,
              "annotations": [], "limitations": list(LIMITATIONS)}
    if remediation is not None:
        bundle["remediation"] = remediation
    raw = canonical(bundle)
    require(len(raw) <= MAX_VIEWER_BYTES, "Viewer export exceeds 5 MiB; select fewer runs")
    _check_viewer_limits(bundle)
    write_new(output, raw)
    return {"project_id": "labproof", "output": str(output), "runs": len(runs), "bytes": len(raw)}
