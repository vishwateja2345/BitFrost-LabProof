"""Product-local verified viewer export; no sibling or integration imports."""
from hashlib import sha256
from pathlib import Path

from .contracts import canonical, check_no_links, parse_json, read_safe, require
from .engine import now, write_new
from .verify_artifacts import verify_artifacts

MAX_VIEWER_BYTES = 5 * 1024 * 1024
LIMITATIONS = [
    "Exported runs passed LabProof's own offline artifact consistency verification.",
    "Unsigned artifacts and hashes do not authenticate sources or prove execution occurred.",
    "The viewer envelope omits raw artifact files; browser inspection is not independent artifact verification.",
    "Incomplete and blocked runs remain incomplete or blocked; no evidence is truncated.",
]


def export_viewer(directories, output):
    require(type(directories) in (list, tuple) and 1 <= len(directories) <= 32, "Export requires 1–32 own run directories")
    output = Path(output).absolute()
    check_no_links(output.parent)
    require(not output.exists(), "Export output already exists")
    runs, seen = [], set()
    for directory in directories:
        root = Path(directory).absolute()
        require(output != root and root not in output.parents, "Export must be outside the verified run")
        before = read_safe(root, "manifest.json")
        verified = verify_artifacts(root)
        manifest_raw = read_safe(root, "manifest.json")
        require(manifest_raw == before, "Manifest changed during export verification")
        manifest = parse_json(manifest_raw)
        require(manifest["run_id"] == verified["run_id"] and manifest["run_id"] not in seen, "Duplicate/changed run identity")
        seen.add(manifest["run_id"])
        entries = {entry["path"]: entry for entry in manifest["artifacts"]}
        selected = {}
        for name in ("report.json", "events.jsonl"):
            raw = read_safe(root, name)
            require(len(raw) == entries[name]["bytes"] and sha256(raw).hexdigest() == entries[name]["sha256"], "Artifact changed during export")
            selected[name] = raw
        events = [parse_json(row) for row in selected["events.jsonl"].splitlines()]
        runs.append({"manifest": manifest, "report": parse_json(selected["report.json"]), "events": events})
        # Bound accumulated output while loading, not only at the eventual write.
        require(len(canonical(runs)) <= MAX_VIEWER_BYTES, "Viewer export exceeds 5 MiB; select fewer runs")
    bundle = {"schema_version": "1.0", "generated_at": now(), "runs": runs,
              "annotations": [], "limitations": list(LIMITATIONS)}
    raw = canonical(bundle)
    require(len(raw) <= MAX_VIEWER_BYTES, "Viewer export exceeds 5 MiB; select fewer runs")
    write_new(output, raw)
    return {"project_id": "labproof", "output": str(output), "runs": len(runs), "bytes": len(raw)}
