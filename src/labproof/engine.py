"""Serial, bounded observe/collect/reset/replay/adjudicate workflow."""
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from . import __version__
from .contracts import canonical, check_no_links, require, validate_manifest
from .evidence import record_evidence
from .policy import Budget, Limits, PHASES, VARIANTS, catalogue_actions
from .report import LIMITATIONS, build_report
from .transport import ReplayTransport


def now():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, data):
    with path.open("xb") as stream:
        stream.write(data)


def run_demo(output: Path, *, limits: Limits | None = None, budget: Budget | None = None, transport=None):
    output = Path(output).absolute()
    check_no_links(output.parent)
    output.mkdir(exist_ok=False)  # No overwrite or misleading resume.
    run_id, created = "lp_" + uuid4().hex, now()
    limits = limits or Limits()
    budget = budget or Budget(limits)
    require(budget.limits == limits, "Budget/configuration mismatch")
    evidence, errors, sequence = [], [], 0
    status = "incomplete"

    def event(kind, data):
        nonlocal sequence
        sequence += 1
        entry = {"sequence": sequence, "type": kind, "run_id": run_id, "timestamp": now(), "data": data}
        with (output / "events.jsonl").open("ab") as stream:
            stream.write(canonical(entry))

    write_new(output / "events.jsonl", b"")
    write_new(output / "errors.jsonl", b"")
    event("run_started", {"mode": "replay"})
    config = {"package_version": __version__, "limits": asdict(limits), "mode": "replay", "fixture_sha256": None,
              "code_sha256": sha256(b"".join(p.name.encode() + b"\0" + p.read_bytes() for p in sorted(Path(__file__).parent.rglob("*.py")))).hexdigest()}
    try:
        transport = transport or ReplayTransport()
        config["fixture_sha256"] = sha256(transport.fixture_bytes).hexdigest()
        write_new(output / "fixture.json", transport.fixture_bytes)
        for phase in PHASES:
            budget.check()
            transport.reset()
            event("snapshot_reset", {"phase": phase, "kind": "frozen_fixture_reload"})
            for variant in VARIANTS:
                for action in catalogue_actions():
                    event("action_selected", {**action.to_dict(), "variant": variant, "phase": phase})
                    response = transport.execute(action, variant=variant, budget=budget)
                    item = record_evidence(output, action, response, variant, phase, config["fixture_sha256"])
                    evidence.append(item)
                    event("evidence_collected", {"evidence_id": item["id"]})
        budget.check()
        status = "completed"
    except KeyboardInterrupt:
        budget.cancelled = True
        status = "cancelled"
        errors.append({"id": "error_1", "type": "cancelled", "message": "Replay interrupted; remaining checks are not tested."})
    except Exception as exc:
        status = "cancelled" if budget.cancelled else "incomplete"
        # Do not serialize arbitrary exception text: it could contain secrets.
        errors.append({"id": "error_1", "type": type(exc).__name__, "message": "Replay stopped; evidence is partial and unperformed checks are not tested."})
    write_new(output / "config.json", canonical(config))
    for error in errors:
        with (output / "errors.jsonl").open("ab") as stream:
            stream.write(canonical(error))
        event("run_error", {"error_id": error["id"]})
    usage = {"tool_attempts": budget.actions, "response_bytes": budget.response_bytes, "model_calls": 0, "model_usage": None, "model_usage_status": "not_applicable_replay"}
    report = build_report(run_id, status, evidence, usage)
    write_new(output / "report.json", canonical(report))
    event("run_completed" if status == "completed" else "run_stopped", {"status": status, "evidence_count": len(evidence)})
    artifacts = []
    for path in sorted(output.rglob("*")):
        if path.is_file():
            raw = path.read_bytes()
            artifacts.append({"path": path.relative_to(output).as_posix(), "sha256": sha256(raw).hexdigest(), "bytes": len(raw)})
    manifest = {"schema_version": "1.0", "project_id": "labproof", "run_id": run_id, "mode": "replay", "status": status, "created_at": created, "artifacts": artifacts, "limitations": LIMITATIONS}
    validate_manifest(manifest)
    write_new(output / "manifest.json", canonical(manifest))
    return manifest
