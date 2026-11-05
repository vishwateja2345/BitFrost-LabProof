"""Fixed synthetic local catalogue; no arbitrary repositories, targets or commands."""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from .adapters import parse_observation
from .contracts import SHA_RE, canonical, check_no_links, parse_json, require, validate_manifest
from .engine import now, write_new
from .local_profiles import OPERATIONS, VARIANTS, build_launch_plan, default_profile
from .local_report import LOCAL_LIMITATIONS, build_local_report


def provisioned_pack(pack_id):
    default_profile(pack_id)
    path = Path(__file__).parent / "fixtures" / "local-provisioning.json"
    check_no_links(path)
    require(path.stat().st_size <= 65536, "Oversized provisioning record")
    provision = parse_json(path.read_bytes())
    require(isinstance(provision, dict) and set(provision) == {"schema_version", "packs"}
            and provision["schema_version"] == "local-provisioning-1", "Invalid provisioning schema")
    require(isinstance(provision["packs"], dict) and pack_id in provision["packs"], "Pack is not provisioned")
    value = provision["packs"][pack_id]
    # This file is installed by the trusted provisioning step, never loaded from
    # imported artifacts or tool responses. Registry requests cannot replace it.
    require(isinstance(value, dict) and set(value) == {"image_id", "base_digest", "fixture_sha256", "worker_sha256"}, "Invalid provisioning entry")
    require(isinstance(value["image_id"], str) and value["image_id"].startswith("sha256:")
            and SHA_RE.fullmatch(value["image_id"][7:]), "Invalid provisioned image")
    for key in ("fixture_sha256", "worker_sha256"):
        require(isinstance(value[key], str) and SHA_RE.fullmatch(value[key]), "Invalid provisioning digest")
    require(isinstance(value["base_digest"], str) and "@sha256:" in value["base_digest"]
            and SHA_RE.fullmatch(value["base_digest"].split("@sha256:")[-1]), "Invalid pinned base")
    return value


def run_local(output, pack_id):
    from .sandbox.runtime import LiveSandboxSession
    profile = default_profile(pack_id)
    operation, language = profile.operation_id, profile.language
    # Reject unmapped profiles before creating a run, even when provisioning is absent.
    build_launch_plan({"schema_version": "1.0", "pack_id": pack_id,
                       "operation_id": operation, "fixture_id": profile.fixture_id,
                       "parameters": {"variant": VARIANTS[0]}}, "sha256:" + "0" * 64)
    output = Path(output).absolute()
    check_no_links(output.parent)
    output.mkdir(exist_ok=False)
    (output / "evidence").mkdir()
    (output / "outputs").mkdir()
    provision_error = None
    try:
        provision = provisioned_pack(pack_id)
    except (OSError, ValueError, KeyError) as error:
        provision_error = error
        provision = None
    plans = []
    if provision is not None:
        for variant in VARIANTS:
            request = {"schema_version": "1.0", "pack_id": pack_id,
                       "operation_id": operation, "fixture_id": profile.fixture_id,
                       "parameters": {"variant": variant}}
            plans.append(build_launch_plan(request, provision["image_id"]))
    limits = profile.limits
    run_id, created = "lp_" + uuid4().hex, now()
    records, executions, errors = [], [], []
    sequence = 0
    accepted = {"accepted": False, "report": None}
    status = "blocked"
    config = {"schema_version": "local-config-1", "pack_id": pack_id,
              "fixture_id": f"{pack_id}-synthetic-v1", "operation_id": operation,
              "image_id": provision["image_id"] if provision is not None else "sha256:" + "0" * 64,
              "fixture_sha256": provision["fixture_sha256"] if provision is not None else "0" * 64,
              "worker_sha256": provision["worker_sha256"] if provision is not None else "0" * 64,
              "limits": asdict(limits), "policy_version": "local-policy-1"}

    def event(kind, data):
        nonlocal sequence
        sequence += 1
        with (output / "events.jsonl").open("ab") as stream:
            stream.write(canonical({"sequence": sequence, "type": kind, "run_id": run_id, "timestamp": now(), "data": data}))

    write_new(output / "events.jsonl", b"")
    write_new(output / "errors.jsonl", b"")
    event("run_started", {"mode": "local", "pack_id": pack_id})
    try:
        if provision_error is not None:
            raise provision_error
        session = LiveSandboxSession(tuple(plans), language=language, limits=limits)
        accepted = {"accepted": True, "report": session.accept()}
        event("containment_checked", {"accepted": True})
        status = "incomplete"
        for phase in ("observation", "verification"):
            for variant in VARIANTS:
                result = session.execute(f"{operation}-{variant}")
                raw = result.output
                execution = {"execution_id": result.execution_id, "reset_id": result.reset_id,
                    "phase": phase, "variant": variant, "operation_id": operation,
                    "image_id": result.image_id, "policy_digest": result.policy_digest, "runtime_id": result.runtime_id,
                    "returncode": result.returncode, "timed_out": result.timed_out, "cancelled": result.cancelled,
                    "truncated": result.truncated, "cleanup_ok": result.cleanup_ok, "elapsed_seconds": result.elapsed_seconds,
                    "output_bytes": len(raw), "raw_sha256": sha256(raw).hexdigest(), "evidence_id": None}
                write_new(output / "outputs" / f"{result.execution_id}.txt", raw)
                executions.append(execution)
                try:
                    require(result.returncode == 0 and not (result.timed_out or result.cancelled or result.truncated)
                            and result.cleanup_ok, "Worker did not finish safely")
                    observation = parse_observation(raw, operation, variant)
                    record = {"phase": phase, "execution_id": result.execution_id, "reset_id": result.reset_id,
                              "observation": observation}
                    record["id"] = "ev_" + sha256(canonical(record)).hexdigest()[:24]
                    execution["evidence_id"] = record["id"]
                    records.append(record)
                    write_new(output / "evidence" / f"{record['id']}.json", canonical(record))
                finally:
                    event("execution_finished", {"execution_id": result.execution_id, "evidence_id": execution["evidence_id"]})
        status = "completed"
    except (Exception, KeyboardInterrupt) as error:
        if not accepted["accepted"]:
            event("containment_checked", {"accepted": False})
        if isinstance(error, KeyboardInterrupt):
            status = "cancelled"
        errors.append({"id": "error_1", "type": type(error).__name__,
                       "message": "Local run stopped; unperformed or failed checks are not successful assessments."})
    for error in errors:
        with (output / "errors.jsonl").open("ab") as stream:
            stream.write(canonical(error))
        event("run_error", {"error_id": error["id"]})
    write_new(output / "config.json", canonical(config))
    write_new(output / "acceptance.json", canonical(accepted))
    write_new(output / "executions.json", canonical(executions))
    report = build_local_report(run_id, status, pack_id, records, executions)
    write_new(output / "report.json", canonical(report))
    event("run_completed" if status == "completed" else "run_stopped", {"status": status, "evidence_count": len(records)})
    artifacts = []
    for path in sorted(output.rglob("*")):
        if path.is_file():
            raw = path.read_bytes()
            artifacts.append({"path": path.relative_to(output).as_posix(), "sha256": sha256(raw).hexdigest(), "bytes": len(raw)})
    manifest = {"schema_version": "1.0", "project_id": "labproof", "run_id": run_id,
                "mode": "local", "status": status, "created_at": created, "artifacts": artifacts,
                "limitations": list(LOCAL_LIMITATIONS)}
    validate_manifest(manifest)
    write_new(output / "manifest.json", canonical(manifest))
    return manifest


def provisioned_experiment(profile):
    """Separate trusted provisioning; old combined fixture hashes cannot upgrade."""
    from .local_experiments import validate_provenance
    path = Path(__file__).parent / "fixtures" / "local-provisioning-v2.json"
    check_no_links(path)
    require(path.stat().st_size <= 65536, "Oversized v2 provisioning record")
    value = parse_json(path.read_bytes())
    require(type(value) is dict and set(value) == {"schema_version", "profiles"}
            and value["schema_version"] == "local-profiles-provisioning-2", "Invalid v2 provisioning")
    require(type(value["profiles"]) is dict and profile.profile_id in value["profiles"], "V2 profile not provisioned")
    from .provisioning import verify_installed_identities
    provenance = validate_provenance(value["profiles"][profile.profile_id])
    return verify_installed_identities(Path(__file__).parent, profile.local.pack_id, provenance)


def run_experiments(output, plan):
    """Explicit opt-in v2. Imported plans only select existing trusted mappings."""
    from .sandbox.runtime import LiveSandboxSession
    from .local_profiles import validate_experiment_plan
    from .local_experiments import (LIMITATIONS, config_for, execution_record, evidence_record,
                                    build_report, can_reserve, is_complete)
    profile = validate_experiment_plan(plan)
    output = Path(output).absolute()
    check_no_links(output.parent)
    output.mkdir(exist_ok=False)
    (output / "evidence").mkdir()
    (output / "outputs").mkdir()
    run_id, created = "lp_" + uuid4().hex, now()
    config = config_for(plan, None)
    accepted = {"accepted": False, "report": None}
    executions, errors, events, attempts = [], [], [], []
    status = "blocked"

    def event(kind, data):
        events.append({"sequence": len(events) + 1, "type": kind, "run_id": run_id,
                       "timestamp": now(), "data": data})

    from .experiment_journal import append_checkpoint
    journal = output / "checkpoints.jsonl"
    write_new(journal, b"")
    append_checkpoint(journal, "started", {"run_id": run_id, "plan": plan})
    event("run_started", {"mode": "local", "pack_id": profile.local.pack_id})
    try:
        config = config_for(plan, provisioned_experiment(profile))
        append_checkpoint(journal, "provisioned", config)
        # Four fixed plans keep the existing accepted canary/policy surface.
        plans = tuple(build_launch_plan({"schema_version": "1.0", "pack_id": profile.local.pack_id,
                    "operation_id": profile.local.operation_id, "fixture_id": profile.local.fixture_id,
                    "parameters": {"variant": variant}}, config["provisioning"]["image_id"]) for variant in VARIANTS)
        session = LiveSandboxSession(plans, language=profile.local.language, limits=profile.local.limits)
        accepted = {"accepted": True, "report": session.accept()}
        append_checkpoint(journal, "accepted", accepted)
        event("containment_checked", {"accepted": True})
        status = "incomplete"
        for step in plan["steps"]:
            require(can_reserve(plan, executions), "Experiment budget reservation exhausted")
            attempts.append({"step_id": step["id"], "execution_id": None})
            append_checkpoint(journal, "attempted", attempts[-1])
            result = session.execute(f"{profile.local.operation_id}-{step['request']['parameters']['variant']}")
            execution = execution_record(step, result, config)
            attempts[-1]["execution_id"] = execution["execution_id"]
            executions.append(execution)
            write_new(output / "outputs" / f"{execution['execution_id']}.txt", result.output)
            append_checkpoint(journal, "returned", execution)
            record = evidence_record(execution)
            if record is not None:
                write_new(output / "evidence" / f"{record['id']}.json", canonical(record))
            event("execution_finished", {"execution_id": execution["execution_id"], "evidence_id": execution["evidence_id"]})
            require(execution["parse_status"] == "parsed", "Worker result incomplete or unrecognized")
        require(is_complete(plan, executions), "Required controls or aggregate budgets incomplete")
        status = "completed"
    except (Exception, KeyboardInterrupt) as error:
        if not accepted["accepted"]:
            event("containment_checked", {"accepted": False})
        if isinstance(error, KeyboardInterrupt):
            status = "cancelled"
        errors.append({"id": "error_1", "type": type(error).__name__,
                       "message": "V2 experiment stopped; missing provisioning, budgets, controls or worker observations are not successful assessments."})
    for error in errors:
        event("run_error", {"error_id": error["id"]})
    append_checkpoint(journal, "finished", {"status": status})
    report = build_report(run_id, status, config, executions, attempts)
    event("run_completed" if status == "completed" else "run_stopped",
          {"status": status, "evidence_count": len(report["evidence"])})
    for name, value in (("config.json", config), ("acceptance.json", accepted),
                        ("executions.json", executions), ("attempts.json", attempts), ("report.json", report)):
        write_new(output / name, canonical(value))
    write_new(output / "events.jsonl", b"".join(canonical(e) for e in events))
    write_new(output / "errors.jsonl", b"".join(canonical(e) for e in errors))
    artifacts = [{"path": p.relative_to(output).as_posix(), "bytes": len(p.read_bytes()),
                  "sha256": sha256(p.read_bytes()).hexdigest()} for p in sorted(output.rglob("*")) if p.is_file()]
    manifest = {"schema_version": "1.0", "project_id": "labproof", "run_id": run_id, "mode": "local",
                "status": status, "created_at": created, "artifacts": artifacts, "limitations": list(LIMITATIONS)}
    validate_manifest(manifest)
    write_new(output / "manifest.json", canonical(manifest))
    return manifest
