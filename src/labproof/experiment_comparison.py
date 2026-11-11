"""Verified fixed-v2 experiment differences; no causal or authenticity claims."""
from hashlib import sha256
from pathlib import Path
import tempfile

from .contracts import canonical, check_no_links, parse_json, read_safe, require, validate_manifest
from .engine import write_new
from .verify_artifacts import verify_artifacts


def _snapshot(directory):
    """Verify the exact private copy used for comparison, not unchecked rereads."""
    root = Path(directory).absolute()
    check_no_links(root)
    # Reject unregistered source files too, then reverify retained snapshot bytes.
    verify_artifacts(root)
    manifest_raw = read_safe(root, "manifest.json")
    manifest = parse_json(manifest_raw)
    validate_manifest(manifest)
    with tempfile.TemporaryDirectory(prefix="labproof-compare-") as scratch:
        copy = Path(scratch).resolve(strict=True)
        write_new(copy / "manifest.json", manifest_raw)
        for row in manifest["artifacts"]:
            raw = read_safe(root, row["path"])
            require(len(raw) == row["bytes"] and sha256(raw).hexdigest() == row["sha256"],
                    "Comparison source changed during snapshot")
            path = copy / row["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            write_new(path, raw)
        verified = verify_artifacts(copy)
        config_raw, report_raw = read_safe(copy, "config.json"), read_safe(copy, "report.json")
        config, report = parse_json(config_raw), parse_json(report_raw)
        require(config.get("schema_version") == "local-config-2"
                and report.get("schema_version") == "local-report-2", "Comparison requires fixed-v2 experiments")
        return {"binding": {"run_id": manifest["run_id"], "manifest_sha256": sha256(manifest_raw).hexdigest(),
                            "config_sha256": sha256(config_raw).hexdigest(), "report_sha256": sha256(report_raw).hexdigest()},
                "complete": verified["complete"], "config": config, "report": report}


def _projections(snapshot):
    config, report = snapshot["config"], snapshot["report"]
    provenance = config["provisioning"]
    return {
        "fixture": None if provenance is None else {k: provenance[k] for k in ("source_sha256", "oracle_sha256")},
        "toolchain": None if provenance is None else {k: provenance[k] for k in
            ("image_id", "base_digest", "worker_sha256", "adapter_sha256", "dependency_lock_sha256",
             "compiler_version", "compiler_flags", "binary_sha256")},
        "configuration": {k: config[k] for k in ("plan", "limits", "parser_id", "grader_id", "policy_version")},
        "controls": report["completion"],
        "observations": [{k: execution[k] for k in ("step_id", "request", "phase", "parse_status", "observation",
                          "controller_status", "child_returncode", "timed_out", "cancelled", "truncated", "cleanup_ok")}
                         for execution in report["experiments"]],
        "verdicts": [{"id": row["id"], "status": row["status"]} for row in report["findings"]],
    }


def compare_experiments(before_directory, after_directory):
    before, after = _snapshot(before_directory), _snapshot(after_directory)
    left, right = _projections(before), _projections(after)
    reasons = []
    if not before["complete"] or not after["complete"]:
        reasons.append("One or both runs are blocked or incomplete.")
    for key in ("profile_id",):
        if before["config"]["plan"][key] != after["config"]["plan"][key]:
            reasons.append("Experiment profiles differ.")
    for key in ("parser_id", "grader_id"):
        if before["config"][key] != after["config"][key]:
            reasons.append("Parser or grader semantics differ.")
    if before["config"]["plan"]["steps"] != after["config"]["plan"]["steps"]:
        reasons.append("Experiment request/control plans differ.")
    changes = {key: {"before": left[key], "after": right[key]} for key in left
               if canonical(left[key]) != canonical(right[key])}
    return {"schema_version": "experiment-comparison-1", "before": before["binding"], "after": after["binding"],
            "status": "not_comparable" if reasons else "comparable", "reasons": reasons,
            "changed_categories": list(changes), "changes": changes,
            "causal_attribution": "not_established",
            "limitations": ["Verified recorded differences, not causal attribution or source authenticity.",
                            "Multiple changed inputs prevent unsupported single-cause claims.",
                            "Fresh worker IDs and elapsed time differences are not semantic observation changes."]}


def verify_comparison(document, before_directory, after_directory):
    require(canonical(document) == canonical(compare_experiments(before_directory, after_directory)),
            "Comparison differs from verified input snapshots")
    return {"valid": True, "assurance": "Recorded differences only; causality and authenticity not established."}
