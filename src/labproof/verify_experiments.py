"""V2-only offline verification; legacy derivation is never a fallback."""
from .contracts import canonical, parse_json, require, timestamp
from .local_profiles import VARIANTS, build_launch_plan, validate_experiment_plan
from .local_experiments import (LIMITATIONS, shape, config_for, validate_execution,
                                build_report, is_complete, can_reserve)
from .sandbox.policy import reviewed_policy_bindings
from .verify_local import _inventory, _acceptance_report, _jsonl, _id


def verify_experiments(root, manifest):
    require(manifest["limitations"] == LIMITATIONS, "V2 limitations mismatch")
    payloads = _inventory(root, manifest)
    config = parse_json(payloads["config.json"])
    expected_config = config_for(config["plan"], config["provisioning"])
    require(canonical(config) == canonical(expected_config), "V2 configuration mismatch")
    profile = validate_experiment_plan(config["plan"])
    acceptance = parse_json(payloads["acceptance.json"])
    shape(acceptance, ("accepted", "report"), "v2 acceptance")
    require(type(acceptance["accepted"]) is bool, "Invalid acceptance flag")
    seen = set()
    if acceptance["accepted"]:
        require(config["provisioning"] is not None, "Accepted run lacks provisioning")
        old_config = {"image_id": config["provisioning"]["image_id"], "pack_id": profile.local.pack_id}
        seen = _acceptance_report(acceptance["report"], old_config, profile.local.limits)
        plans = [build_launch_plan({"schema_version": "1.0", "pack_id": profile.local.pack_id,
                 "operation_id": profile.local.operation_id, "fixture_id": profile.local.fixture_id,
                 "parameters": {"variant": v}}, old_config["image_id"]) for v in VARIANTS]
        require(tuple(acceptance["report"]["policy_digests"]) in reviewed_policy_bindings(plans, profile.local.limits),
                "Acceptance does not bind trusted launch policies")
    else:
        require(acceptance["report"] is None, "Unaccepted run contains acceptance report")
    executions = parse_json(payloads["executions.json"])
    attempts = parse_json(payloads["attempts.json"])
    plan = config["plan"]
    require(type(executions) is list and len(executions) <= len(plan["steps"]), "Invalid v2 executions")
    require(type(attempts) is list and len(executions) <= len(attempts) <= min(len(executions) + 1, len(plan["steps"])), "Invalid attempt accounting")
    require(not attempts or acceptance["accepted"], "Attempt without containment acceptance")
    require(len(attempts) <= plan["budgets"]["actions"], "Action budget exceeded")
    for index, attempt in enumerate(attempts):
        shape(attempt, ("step_id", "execution_id"), "v2 attempt")
        require(attempt["step_id"] == plan["steps"][index]["id"], "Attempt order mismatch")
        require(attempt["execution_id"] == (executions[index]["execution_id"] if index < len(executions) else None), "Attempt/execution mismatch")
        require(can_reserve(plan, executions[:index]), "Attempt exceeds resource reservation")
    expected_files = {"config.json", "acceptance.json", "executions.json", "attempts.json", "report.json", "events.jsonl", "errors.jsonl"}
    records = []
    for index, execution in enumerate(executions):
        _id(execution["execution_id"])
        path = f"outputs/{execution['execution_id']}.txt"
        expected_files.add(path)
        record = validate_execution(execution, plan["steps"][index], config, payloads[path], seen)
        require(execution["runtime_id"] == acceptance["report"]["runtime_id"], "Runtime acceptance mismatch")
        variant_index = VARIANTS.index(execution["request"]["parameters"]["variant"])
        require(execution["policy_digest"] == acceptance["report"]["policy_digests"][variant_index], "Policy acceptance mismatch")
        require(execution["parse_status"] == "parsed" or index == len(attempts) - 1, "Continued after incomplete worker")
        if record is not None:
            path = f"evidence/{record['id']}.json"
            expected_files.add(path)
            require(canonical(parse_json(payloads[path])) == canonical(record), "V2 evidence/raw mismatch")
            records.append(record)
    # Legacy v2 artifacts predate durable checkpoints. When present, every row
    # must be rederived; an unfinished journal alone never verifies as a run.
    if "checkpoints.jsonl" in payloads:
        from .experiment_journal import expected_checkpoints
        expected_files.add("checkpoints.jsonl")
        checkpoints = _jsonl(payloads["checkpoints.jsonl"])
        expected = expected_checkpoints(manifest["run_id"], config, acceptance, attempts, executions, manifest["status"])
        require(canonical(checkpoints) == canonical(expected), "Experiment checkpoint mismatch")
    require(set(payloads) == expected_files, "Unreferenced or missing v2 artifacts")
    errors = _jsonl(payloads["errors.jsonl"])
    require(len(errors) <= 1, "Too many v2 errors")
    for error in errors:
        shape(error, ("id", "type", "message"), "v2 error")
        require(error["id"] == "error_1", "Invalid v2 error ID")
        require(all(type(error[k]) is str and 0 < len(error[k]) <= 1000 for k in ("type", "message")), "Invalid v2 error")
    complete = manifest["status"] == "completed"
    if complete:
        require(acceptance["accepted"] and not errors and len(attempts) == len(executions) and is_complete(plan, executions), "V2 completion lacks required controls or budgets")
    else:
        require(bool(errors), "Incomplete v2 run requires error")
        require(manifest["status"] in (("incomplete", "cancelled") if acceptance["accepted"] else ("blocked", "cancelled")), "V2 stop status mismatch")
    report = parse_json(payloads["report.json"])
    require(canonical(report) == canonical(build_report(manifest["run_id"], manifest["status"], config, executions, attempts)), "V2 report derivation mismatch")
    expected_events = [("run_started", {"mode": "local", "pack_id": profile.local.pack_id}),
                       ("containment_checked", {"accepted": acceptance["accepted"]})]
    expected_events += [("execution_finished", {"execution_id": e["execution_id"], "evidence_id": e["evidence_id"]}) for e in executions]
    expected_events += [("run_error", {"error_id": e["id"]}) for e in errors]
    expected_events += [("run_completed" if complete else "run_stopped", {"status": manifest["status"], "evidence_count": len(records)})]
    events = _jsonl(payloads["events.jsonl"])
    require(len(events) == len(expected_events), "V2 event count mismatch")
    last = timestamp(manifest["created_at"])
    for index, (event, (kind, data)) in enumerate(zip(events, expected_events), 1):
        shape(event, "sequence type run_id timestamp data".split(), "v2 event")
        require(type(event["sequence"]) is int and event["sequence"] == index and event["run_id"] == manifest["run_id"], "V2 event identity mismatch")
        require(event["type"] == kind and canonical(event["data"]) == canonical(data), "V2 event order/data mismatch")
        current = timestamp(event["timestamp"])
        require(current >= last, "V2 event timestamp moved backwards")
        last = current
    return {"valid": True, "project_id": "labproof", "run_id": manifest["run_id"], "status": manifest["status"],
            "complete": complete, "artifact_count": len(payloads),
            "limitation": "Internal consistency only; unsigned records are not authenticity or proof that execution occurred."}
