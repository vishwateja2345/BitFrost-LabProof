"""Narrow v2 record derivation for the existing synthetic local adapters.

Pure host code: no fixture execution, dynamic adapters or imported registrations.
New tool families require their own reviewed parser/profile and runtime acceptance.
"""
from dataclasses import asdict
from hashlib import sha256
import re

from .adapters import ObservationError, parse_observation, adjudicate_observations
from .contracts import ID_RE, SHA_RE, canonical, require
from .local_profiles import PHASES, canonical_request_key, validate_experiment_plan
from .local_report import LOCAL_LIMITATIONS, LOCAL_PROVENANCE

LIMITATIONS = [*LOCAL_LIMITATIONS,
    "V2 is a bounded experiment foundation for existing synthetic adapters, not acceptance of new tool capabilities.",
    "Target invocation, rejection and shrink measurements are unknown for legacy adapters; null is not zero.",
    "Worker-visible source and host-only oracle provenance are separate unsigned host assertions."]
PROVENANCE_FIELDS = set("schema_version image_id base_digest source_sha256 oracle_sha256 worker_sha256 adapter_sha256 dependency_lock_sha256 compiler_version compiler_flags binary_sha256".split())
EXECUTION_FIELDS = set("step_id request request_key phase replay_of execution_id container_id reset_id image_id runtime_id policy_digest provenance_sha256 controller_status child_returncode timed_out cancelled truncated cleanup_ok elapsed_seconds output_bytes raw_sha256 parse_status observation evidence_id".split())


def shape(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), "Invalid " + label + " fields")


def digest(value):
    require(type(value) is str and SHA_RE.fullmatch(value), "Invalid v2 digest")


def identity(value):
    require(type(value) is str and ID_RE.fullmatch(value), "Invalid v2 identity")


def validate_provenance(value):
    shape(value, PROVENANCE_FIELDS, "v2 provenance")
    require(value["schema_version"] == "local-provisioning-2", "Unsupported provisioning version")
    require(type(value["image_id"]) is str and re.fullmatch(r"sha256:[a-f0-9]{64}", value["image_id"]), "Invalid image identity")
    require(type(value["base_digest"]) is str and re.fullmatch(r"[a-z0-9./:_-]+@sha256:[a-f0-9]{64}", value["base_digest"]), "Invalid pinned base")
    for name in ("source_sha256", "oracle_sha256", "worker_sha256", "adapter_sha256"):
        digest(value[name])
    for name in ("dependency_lock_sha256", "binary_sha256"):
        if value[name] is not None:
            digest(value[name])
    require(value["compiler_version"] is None or type(value["compiler_version"]) is str and 0 < len(value["compiler_version"]) <= 100, "Invalid compiler version")
    flags = value["compiler_flags"]
    require(flags is None or type(flags) is list and len(flags) <= 32 and all(type(f) is str and 0 < len(f) <= 100 for f in flags), "Invalid compiler flags")
    return value


def config_for(plan, provenance):
    profile = validate_experiment_plan(plan)
    if provenance is not None:
        validate_provenance(provenance)
    return {"schema_version": "local-config-2", "policy_version": "local-policy-2",
            "plan": plan, "pack_id": profile.local.pack_id, "limits": asdict(profile.local.limits),
            "parser_id": profile.parser_id, "grader_id": profile.grader_id,
            "provisioning": provenance, "provenance_sha256": None if provenance is None else sha256(canonical(provenance)).hexdigest()}


def parse_result(raw, execution, profile):
    safe = (execution["controller_status"] == "completed" and
            execution["child_returncode"] in profile.exit_codes and execution["cleanup_ok"] and
            not any(execution[k] for k in ("timed_out", "cancelled", "truncated")))
    if not safe:
        return "unavailable", None
    try:
        return "parsed", parse_observation(raw, execution["request"]["operation_id"], execution["request"]["parameters"]["variant"])
    except ObservationError:
        return "unrecognized", None


def evidence_record(execution):
    if execution["observation"] is None:
        return None
    fields = "step_id request request_key phase replay_of execution_id container_id reset_id image_id policy_digest runtime_id provenance_sha256 raw_sha256 observation".split()
    body = {k: execution[k] for k in fields}
    return {"id": "ev_" + sha256(canonical(body)).hexdigest()[:24], **body}


def execution_record(step, result, config):
    profile = validate_experiment_plan(config["plan"])
    interrupted = result.timed_out or result.cancelled or result.truncated or not result.cleanup_ok
    record = {"step_id": step["id"], "request": step["request"],
              "request_key": canonical_request_key(step["request"], step["phase"]),
              "phase": step["phase"], "replay_of": step["replay_of"],
              **{k: getattr(result, k) for k in ("execution_id", "container_id", "reset_id", "image_id", "runtime_id", "policy_digest", "timed_out", "cancelled", "truncated", "cleanup_ok", "elapsed_seconds")},
              "provenance_sha256": config["provenance_sha256"],
              "controller_status": "interrupted" if interrupted else "completed",
              "child_returncode": result.returncode, "output_bytes": len(result.output),
              "raw_sha256": sha256(result.output).hexdigest()}
    record["parse_status"], record["observation"] = parse_result(result.output, record, profile)
    evidence = evidence_record(record)
    record["evidence_id"] = None if evidence is None else evidence["id"]
    return record


def accounting(plan, executions):
    return {"tool_attempts": len(executions), "model_calls": 0, "model_usage": None,
            "model_usage_status": "not_applicable_deterministic",
            "completed_steps": sum(e["parse_status"] == "parsed" for e in executions),
            "parsed_observations": sum(e["observation"] is not None for e in executions),
            "replays": sum(e["phase"] == "verification" for e in executions),
            "target_invocations": None, "rejections": None, "shrinks": None,
            "elapsed_seconds": sum(e["elapsed_seconds"] for e in executions),
            "output_bytes": sum(e["output_bytes"] for e in executions)}


def completion_for(plan, executions):
    profile = validate_experiment_plan(plan)
    done = {(e["request"]["parameters"]["variant"], e["phase"]) for e in executions if e["parse_status"] == "parsed"}
    missing = [f"{phase}_{variant}" for variant in profile.required_variants for phase in PHASES if (variant, phase) not in done]
    usage = accounting(plan, executions)
    within = (usage["tool_attempts"] <= plan["budgets"]["actions"] and
              usage["elapsed_seconds"] <= plan["budgets"]["wall_seconds"] and
              usage["output_bytes"] <= plan["budgets"]["output_bytes"])
    return {"required_controls": [f"{phase}_{variant}" for variant in profile.required_variants for phase in PHASES],
            "missing_controls": missing, "all_steps_completed": len(executions) == len(plan["steps"]) and all(e["parse_status"] == "parsed" for e in executions),
            "within_budgets": within}


def is_complete(plan, executions):
    completion = completion_for(plan, executions)
    return completion["all_steps_completed"] and completion["within_budgets"] and not completion["missing_controls"]


def can_reserve(plan, executions):
    limits = validate_experiment_plan(plan).local.limits
    usage = accounting(plan, executions)
    return (usage["tool_attempts"] + 1 <= plan["budgets"]["actions"] and
            usage["elapsed_seconds"] + limits.wall_seconds + limits.cleanup_seconds <= plan["budgets"]["wall_seconds"] and
            usage["output_bytes"] + limits.output_bytes <= plan["budgets"]["output_bytes"])


def build_report(run_id, status, config, executions, attempts):
    profile = validate_experiment_plan(config["plan"])
    records = [evidence_record(e) for e in executions if e["evidence_id"] is not None]
    legacy = [{k: r[k] for k in ("id", "phase", "execution_id", "reset_id", "observation")} for r in records]
    findings = adjudicate_observations(legacy, pack_id=profile.local.pack_id)
    complete = completion_for(config["plan"], executions)
    # No partially performed experiment plan may promote a scoped confirmation.
    if status != "completed" or not is_complete(config["plan"], executions):
        for finding in findings:
            if finding["status"] == "confirmed":
                finding.update(status="inconclusive", observed="Required experiment completion or budgets are not satisfied.")
    usage = accounting(config["plan"], executions)
    steps = {step["id"]: step for step in config["plan"]["steps"]}
    usage.update(tool_attempts=len(attempts), unreturned_attempts=len(attempts) - len(executions),
                 replays=sum(steps[a["step_id"]]["phase"] == "verification" for a in attempts),
                 completed_replays=sum(e["phase"] == "verification" and e["parse_status"] == "parsed" for e in executions))
    if len(attempts) != len(executions):
        # A controller failure provides no worker timing or invocation counts.
        usage["elapsed_seconds"] = None
    return {"schema_version": "local-report-2", "project_id": "labproof", "run_id": run_id,
            "mode": "local", "status": status, "pack_id": profile.local.pack_id,
            "title": f"LabProof v2 local {profile.local.pack_id} synthetic experiments",
            "summary": f"{status}: {len(records)} retained observations; {sum(f['status'] == 'confirmed' for f in findings)} scoped confirmed findings.",
            "limitations": list(LIMITATIONS), "provenance": {**LOCAL_PROVENANCE, "adjudication": profile.grader_id, "provisioning": config["provisioning"]},
            "public_remediation_claims": [], "plan": config["plan"], "experiments": executions,
            "completion": complete, "usage": usage, "findings": findings,
            "evidence": [{"id": r["id"], "title": f"{r['request']['operation_id']} {r['step_id']}",
                          "content": r["observation"]["raw_text"], "artifact_path": f"evidence/{r['id']}.json", "record": r} for r in records]}


def validate_execution(execution, step, config, raw, seen):
    profile = validate_experiment_plan(config["plan"])
    shape(execution, EXECUTION_FIELDS, "v2 execution")
    for field, expected in (("step_id", step["id"]), ("request", step["request"]), ("phase", step["phase"]), ("replay_of", step["replay_of"]),
                            ("request_key", canonical_request_key(step["request"], step["phase"])),
                            ("provenance_sha256", config["provenance_sha256"]), ("image_id", config["provisioning"]["image_id"])):
        require(canonical(execution[field]) == canonical(expected), "Execution/request/config identity mismatch")
    own_ids = set()
    for key in ("execution_id", "container_id", "reset_id"):
        identity(execution[key])
        require(execution[key] not in seen, "Reused worker/reset identity")
        own_ids.add(execution[key])
    seen.update(own_ids)
    for key in ("runtime_id", "policy_digest", "raw_sha256"):
        digest(execution[key])
    for key in ("timed_out", "cancelled", "truncated", "cleanup_ok"):
        require(type(execution[key]) is bool, "Invalid execution flag")
    rc = execution["child_returncode"]
    require(rc is None or type(rc) is int and -2147483648 <= rc <= 2147483647, "Invalid child exit")
    interrupted = any(execution[k] for k in ("timed_out", "cancelled", "truncated")) or not execution["cleanup_ok"]
    require(execution["controller_status"] == ("interrupted" if interrupted else "completed"), "Controller status mismatch")
    elapsed = execution["elapsed_seconds"]
    require(type(elapsed) in (int, float) and 0 <= elapsed <= 86400, "Invalid elapsed time")
    require(type(execution["output_bytes"]) is int and 0 <= execution["output_bytes"] <= profile.local.limits.output_bytes, "Invalid output budget")
    require(execution["output_bytes"] == len(raw) and execution["raw_sha256"] == sha256(raw).hexdigest(), "Raw output binding mismatch")
    parse_status, observation = parse_result(raw, execution, profile)
    require(execution["parse_status"] == parse_status and canonical(execution["observation"]) == canonical(observation), "Parsed observation mismatch")
    record = evidence_record(execution)
    require(execution["evidence_id"] == (None if record is None else record["id"]), "V2 evidence identity mismatch")
    return record
