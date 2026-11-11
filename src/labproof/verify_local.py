"""Pure local-artifact consistency checks; never start or import a worker.

Retained runtime acceptance is an unsigned assertion, not authentication or
independent proof that a container or its containment checks actually ran.
"""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import re

from .adapters import ObservationError, parse_observation
from .contracts import (ID_RE, SHA_RE, MAX_FILES, ValidationError, canonical,
                        check_no_links, parse_json, read_safe, require,
                        timestamp, validate_manifest)
from .local_report import build_local_report, LOCAL_LIMITATIONS
from .sandbox.policy import SandboxLimits

PHASES = ("observation", "verification")
VARIANTS = ("alpha", "beta", "gamma", "delta")
OPERATIONS = {"python": "python-invariants", "typescript": "typescript-node-test",
              "c": "c-gcc", "rust": "rust-cargo-test"}
EXECUTION_FIELDS = set("execution_id reset_id phase variant operation_id image_id policy_digest runtime_id returncode timed_out cancelled truncated cleanup_ok elapsed_seconds output_bytes raw_sha256 evidence_id".split())


def _shape(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), f"Invalid {label} fields")


def _id(value):
    require(type(value) is str and ID_RE.fullmatch(value), "Invalid local identity")


def _digest(value):
    require(type(value) is str and SHA_RE.fullmatch(value), "Invalid local digest")


def _jsonl(raw):
    if not raw:
        return []
    require(raw.endswith(b"\n"), "JSONL missing final newline")
    rows = raw.splitlines()
    require(len(rows) <= 100 and all(rows), "Invalid JSONL records")
    return [parse_json(row) for row in rows]


def _inventory(root, manifest):
    payloads = {}
    for entry in manifest["artifacts"]:
        raw = read_safe(root, entry["path"])
        require(len(raw) == entry["bytes"] and sha256(raw).hexdigest() == entry["sha256"], "Artifact size/digest mismatch")
        payloads[entry["path"]] = raw
    actual = set()
    for number, path in enumerate(root.rglob("*")):
        require(number < MAX_FILES * 2, "Too many directory entries")
        check_no_links(path)
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
        else:
            require(path.is_dir(), "Special filesystem entry forbidden")
    require(actual == set(payloads) | {"manifest.json"}, "Unregistered or missing files")
    return payloads


def _acceptance_report(report, config, limits):
    """Check retained assertions against each other, not against a live runtime."""
    _shape(report, "runtime_id image_id policy_digests canaries timeout_cleanup output_bounded timeout_check output_check limitations".split(), "runtime acceptance report")
    _digest(report["runtime_id"])
    require(report["image_id"] == config["image_id"], "Acceptance/config image mismatch")
    policies = report["policy_digests"]
    require(type(policies) is list and len(policies) == 4, "Expected four variant policy bindings")
    for policy in policies:
        _digest(policy)
    require(len(set(policies)) == 4, "Duplicate variant policy binding")
    require(report["timeout_cleanup"] is True and report["output_bounded"] is True, "Containment acceptance controls not satisfied")
    require(type(report["limitations"]) is list and bool(report["limitations"])
            and all(type(v) is str and v for v in report["limitations"]), "Missing acceptance limitations")
    canaries = report["canaries"]
    require(type(canaries) is list and len(canaries) == 2, "Expected repeated containment canaries")
    workers = set()
    expected = {"uid": 65532, "gid": 65532, "root_write_denied": True,
                "fresh": True, "cap_eff": "0000000000000000", "cap_bnd": "0000000000000000",
                "nnp": "1", "interfaces": ["lo"], "socket_absent": True,
                "memory": str(limits.memory_bytes), "swap": "0", "pids": str(limits.pids), "tmp_type": "tmpfs"}
    native = config["pack_id"] in ("c", "rust")
    mount_fields = set()
    if native:
        expected.update(network_none=True, tmp_noexec=True)
    if limits.output_executable:
        expected.update(output_fresh=True, output_exec=True, scratch_noexec=True,
                        output_type="tmpfs", scratch_type="tmpfs")
        mount_fields = {"output_options", "output_bytes", "scratch_options", "scratch_bytes"}
    for canary in canaries:
        _shape(canary, ("worker", "observations"), "canary")
        _id(canary["worker"])
        require(canary["worker"] not in workers, "Reused containment canary worker")
        workers.add(canary["worker"])
        observations = canary["observations"]
        _shape(observations, set(expected) | {"env", "cpu", "tmp_options", "tmp_bytes"} | mount_fields, "canary observations")
        require(all(canonical(observations[k]) == canonical(v) for k, v in expected.items()), "Retained canary controls inconsistent")
        require(type(observations["env"]) is dict and all(type(k) is str and type(v) is str for k, v in observations["env"].items()), "Invalid canary environment")
        allowed = {"PATH", "HOSTNAME", "HOME", "TMPDIR", "LANG", "LC_CTYPE", "PYTHON_VERSION",
                   "PYTHON_SHA256", "PYTHON_PIP_VERSION", "PYTHON_GET_PIP_URL", "PYTHON_GET_PIP_SHA256",
                   "GPG_KEY", "NODE_VERSION", "YARN_VERSION", "PYTHONDONTWRITEBYTECODE"}
        if native:
            allowed |= {"GCC_VERSION", "GCC_KEYS", "GCC_MIRRORS", "GPG_KEYS", "RUST_VERSION", "RUSTUP_HOME",
                        "CARGO_HOME", "CARGO_NET_OFFLINE", "PWD"}
        require(set(observations["env"]) <= allowed, "Unreviewed retained environment")
        if "GPG_KEYS" in observations["env"]:
            value = observations["env"]["GPG_KEYS"]
            keys = [key for key in value.replace("\t", " ").split(" ") if key]
            require(len(value) <= 2048 and 1 <= len(keys) <= 32
                    and all(re.fullmatch(r"[0-9A-Fa-f]{40}", key) for key in keys),
                    "Invalid retained GCC signing keys")
        exact_env = {"PYTHONDONTWRITEBYTECODE": "1", "CARGO_NET_OFFLINE": "true",
                     "CARGO_HOME": "/usr/local/cargo", "RUSTUP_HOME": "/usr/local/rustup", "PWD": "/tmp"}
        require(all(k not in exact_env or v == exact_env[k] for k, v in observations["env"].items()),
                "Retained environment value mismatch")
        cpu = observations["cpu"]
        require(type(cpu) is str and re.fullmatch(r"[0-9]{1,12} [0-9]{1,12}", cpu.strip()), "Invalid retained CPU quota")
        quota, period = map(int, cpu.split())
        require(quota > 0 and period > 0 and quota <= period * limits.cpus, "Retained CPU limit mismatch")
        options = observations["tmp_options"]
        require(type(options) is list and all(type(v) is str for v in options)
                and {"noexec", "nosuid", "nodev"} <= set(options), "Retained scratch policy mismatch")
        size = observations["tmp_bytes"]
        require(type(size) is int and 0 < size <= limits.scratch_bytes, "Retained scratch size mismatch")
        if limits.output_executable:
            for mount in ("output", "scratch"):
                options = observations[mount + "_options"]
                require(type(options) is list and all(type(v) is str for v in options)
                        and {"nosuid", "nodev"} <= set(options), "Retained native mount protections mismatch")
                require(("noexec" not in options) if mount == "output" else ("noexec" in options),
                        "Retained native executable scope mismatch")
                size = observations[mount + "_bytes"]
                require(type(size) is int and 0 < size <= limits.scratch_bytes, "Retained native mount size mismatch")
    check_policies = set(policies)
    for name, flag in (("timeout_check", "timed_out"), ("output_check", "truncated")):
        check = report[name]
        fields = {"container_id", "policy_digest", "elapsed_seconds", "cleanup_ok", flag}
        if name == "output_check":
            fields.add("output_bytes")
        _shape(check, fields, "retained lifecycle check")
        _id(check["container_id"])
        require(check["container_id"] not in workers, "Reused lifecycle check worker")
        workers.add(check["container_id"])
        _digest(check["policy_digest"])
        require(check["policy_digest"] not in check_policies, "Reused lifecycle check policy")
        check_policies.add(check["policy_digest"])
        require(check[flag] is True and check["cleanup_ok"] is True, "Retained lifecycle check did not pass")
        elapsed = check["elapsed_seconds"]
        require(type(elapsed) in (int, float) and 0 <= elapsed <= 86400, "Invalid lifecycle check elapsed time")
        if name == "output_check":
            require(type(check["output_bytes"]) is int and check["output_bytes"] == limits.output_bytes,
                    "Retained output limit mismatch")
    return workers


def _verify(root, *, expected_manifest=None):
    root = Path(root).absolute()
    check_no_links(root)
    require(root.is_dir(), "Run directory missing")
    raw = read_safe(root, "manifest.json")
    require(expected_manifest is None or raw == expected_manifest, "Manifest changed before local verification")
    manifest = parse_json(raw)
    validate_manifest(manifest)
    require(manifest["mode"] == "local", "Expected local run")
    versioned_config = parse_json(read_safe(root, "config.json"))
    if type(versioned_config) is dict and versioned_config.get("schema_version") == "local-config-2":
        from .verify_experiments import verify_experiments
        return verify_experiments(root, manifest)
    require(manifest["limitations"] == LOCAL_LIMITATIONS, "Local limitations mismatch")
    payloads = _inventory(root, manifest)
    config = parse_json(payloads["config.json"])
    _shape(config, "schema_version pack_id fixture_id operation_id image_id fixture_sha256 worker_sha256 limits policy_version".split(), "local config")
    require(config["schema_version"] == "local-config-1" and config["policy_version"] == "local-policy-1", "Unsupported local config")
    require(type(config["pack_id"]) is str and config["pack_id"] in OPERATIONS, "Unknown local pack")
    require(config["operation_id"] == OPERATIONS[config["pack_id"]], "Operation/pack mismatch")
    require(config["fixture_id"] == f"{config['pack_id']}-synthetic-v1", "Fixture/pack mismatch")
    require(type(config["image_id"]) is str and re.fullmatch(r"sha256:[a-f0-9]{64}", config["image_id"]), "Invalid local image identity")
    _digest(config["fixture_sha256"])
    _digest(config["worker_sha256"])
    limit_fields = set(asdict(SandboxLimits()))
    # The original Python/TypeScript artifacts predate this explicit false flag.
    if (config["pack_id"] in ("python", "typescript") and type(config["limits"]) is dict
            and "output_executable" not in config["limits"]):
        limit_fields.remove("output_executable")
    _shape(config["limits"], limit_fields, "sandbox limits")
    limits = SandboxLimits(**config["limits"])
    require(limits.output_executable is (config["pack_id"] == "rust"),
            "Executable output policy does not match local pack")
    from .local_profiles import VARIANTS as REVIEWED_VARIANTS, build_launch_plan, default_profile
    from .sandbox.policy import reviewed_policy_bindings
    profile = default_profile(config["pack_id"])
    require(limits == profile.limits, "Sandbox limits differ from reviewed local profile")
    plans = [build_launch_plan({"schema_version": "1.0", "pack_id": config["pack_id"],
             "operation_id": profile.operation_id, "fixture_id": profile.fixture_id,
             "parameters": {"variant": variant}}, config["image_id"]) for variant in REVIEWED_VARIANTS]
    acceptance = parse_json(payloads["acceptance.json"])
    _shape(acceptance, ("accepted", "report"), "retained acceptance")
    require(type(acceptance["accepted"]) is bool, "Invalid retained acceptance flag")
    require(type(acceptance["report"]) is dict if acceptance["accepted"] else acceptance["report"] is None,
            "Invalid retained acceptance report")
    if config["image_id"] == "sha256:" + "0" * 64:
        require(config["fixture_sha256"] == "0" * 64 and config["worker_sha256"] == "0" * 64
                and not acceptance["accepted"], "Unprovisioned local config cannot be accepted")
    canary_workers = _acceptance_report(acceptance["report"], config, limits) if acceptance["accepted"] else set()
    if acceptance["accepted"]:
        require(tuple(acceptance["report"]["policy_digests"]) in reviewed_policy_bindings(plans, limits),
                "Acceptance does not bind trusted launch policies")
    executions = parse_json(payloads["executions.json"])
    require(type(executions) is list and len(executions) <= 8, "Invalid execution array")
    expected_files = {"config.json", "report.json", "events.jsonl", "errors.jsonl", "acceptance.json", "executions.json"}
    execution_ids, reset_ids, evidence_ids, records = set(), set(), set(), []
    slots = [(phase, variant) for phase in PHASES for variant in VARIANTS]
    all_success = True
    for number, execution in enumerate(executions):
        _shape(execution, EXECUTION_FIELDS, "execution")
        for key, seen in (("execution_id", execution_ids), ("reset_id", reset_ids)):
            _id(execution[key])
            require(execution[key] not in seen, "Reused execution/reset identity")
            seen.add(execution[key])
        require((execution["phase"], execution["variant"]) == slots[number], "Execution catalogue ordering mismatch")
        require(execution["operation_id"] == config["operation_id"] and execution["image_id"] == config["image_id"], "Execution/config identity mismatch")
        _digest(execution["policy_digest"])
        _digest(execution["runtime_id"])
        require(acceptance["accepted"], "Execution without retained acceptance")
        require(execution["runtime_id"] == acceptance["report"]["runtime_id"]
                and execution["policy_digest"] == acceptance["report"]["policy_digests"][number % 4],
                "Execution/acceptance identity mismatch")
        require(execution["execution_id"] not in canary_workers and execution["reset_id"] not in canary_workers,
                "Execution reuses a containment canary identity")
        for flag in ("timed_out", "cancelled", "truncated", "cleanup_ok"):
            require(type(execution[flag]) is bool, "Invalid execution flag")
        rc = execution["returncode"]
        require(rc is None or type(rc) is int and -2147483648 <= rc <= 2147483647, "Invalid return code")
        elapsed = execution["elapsed_seconds"]
        require(type(elapsed) in (int, float) and 0 <= elapsed <= 86400, "Invalid elapsed time")
        count = execution["output_bytes"]
        require(type(count) is int and 0 <= count <= limits.output_bytes, "Output budget exceeded")
        _digest(execution["raw_sha256"])
        raw_path = f"outputs/{execution['execution_id']}.txt"
        expected_files.add(raw_path)
        raw = payloads[raw_path]
        require(len(raw) == count and sha256(raw).hexdigest() == execution["raw_sha256"], "Execution output binding mismatch")
        successful = rc == 0 and not any(execution[k] for k in ("timed_out", "cancelled", "truncated")) and execution["cleanup_ok"]
        evidence_id = execution["evidence_id"]
        if evidence_id is not None:
            require(successful, "Failed execution cannot supply evidence")
            _id(evidence_id)
            require(evidence_id not in evidence_ids, "Duplicate evidence binding")
            evidence_ids.add(evidence_id)
            relative = f"evidence/{evidence_id}.json"
            expected_files.add(relative)
            record = parse_json(payloads[relative])
            _shape(record, "id phase execution_id reset_id observation".split(), "observation record")
            require(record["id"] == evidence_id and all(record[k] == execution[k] for k in ("phase", "execution_id", "reset_id")), "Evidence/execution identity mismatch")
            body = {key: value for key, value in record.items() if key != "id"}
            require(evidence_id == "ev_" + sha256(canonical(body)).hexdigest()[:24], "Evidence content ID mismatch")
            require(record["observation"] == parse_observation(raw, execution["operation_id"], execution["variant"]), "Evidence/raw observation mismatch")
            records.append(record)
        else:
            if successful:
                try:
                    parse_observation(raw, execution["operation_id"], execution["variant"])
                except ObservationError:
                    pass
                else:
                    raise ValidationError("Successful parseable execution is missing evidence")
            all_success = False
        all_success = all_success and successful
        require(evidence_id is not None or number == len(executions) - 1,
                "Executions continued after a failed observation")
    require(not executions or acceptance["accepted"], "Execution without retained acceptance")
    require(set(payloads) == expected_files, "Unreferenced or missing local artifacts")
    errors = _jsonl(payloads["errors.jsonl"])
    require(len(errors) <= 16, "Too many run errors")
    error_ids = set()
    for error in errors:
        _shape(error, ("id", "type", "message"), "error")
        _id(error["id"])
        require(error["id"] not in error_ids, "Duplicate error ID")
        require(all(type(error[k]) is str and 0 < len(error[k]) <= 1000 for k in ("type", "message")), "Invalid run error")
        error_ids.add(error["id"])
    completed = manifest["status"] == "completed"
    if completed:
        require(acceptance["accepted"] and len(executions) == 8 and len(records) == 8 and all_success and not errors, "Completed local run lacks successful execution evidence")
    else:
        require(bool(errors), "Incomplete run requires an error")
    report = parse_json(payloads["report.json"])
    expected_report = build_local_report(manifest["run_id"], manifest["status"], config["pack_id"], records, executions)
    require(canonical(report) == canonical(expected_report), "Local report differs from deterministic evidence derivation")
    expected_events = [("run_started", {"mode": "local", "pack_id": config["pack_id"]}),
                       ("containment_checked", {"accepted": acceptance["accepted"]})]
    expected_events += [("execution_finished", {"execution_id": e["execution_id"], "evidence_id": e["evidence_id"]}) for e in executions]
    expected_events += [("run_error", {"error_id": e["id"]}) for e in errors]
    expected_events += [("run_completed" if completed else "run_stopped", {"status": manifest["status"], "evidence_count": len(records)})]
    events = _jsonl(payloads["events.jsonl"])
    require(len(events) == len(expected_events), "Missing or extra local events")
    last_time = timestamp(manifest["created_at"])
    for sequence, (event, (kind, data)) in enumerate(zip(events, expected_events), 1):
        _shape(event, "sequence type run_id timestamp data".split(), "event")
        require(type(event["sequence"]) is int and event["sequence"] == sequence, "Event sequence gap")
        require(event["run_id"] == manifest["run_id"], "Event run identity mismatch")
        require(event["type"] == kind and canonical(event["data"]) == canonical(data), "Event ordering/data mismatch")
        current = timestamp(event["timestamp"])
        require(current >= last_time, "Event timestamp moved backwards")
        last_time = current
    return {"valid": True, "project_id": "labproof", "run_id": manifest["run_id"],
            "status": manifest["status"], "complete": completed, "artifact_count": len(payloads),
            "limitation": "Internal consistency only; unsigned runtime/canary records are not authenticity or proof that execution occurred."}


def verify_local(root, *, expected_manifest=None):
    try:
        return _verify(root, expected_manifest=expected_manifest)
    except ValidationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError) as exc:
        raise ValidationError(f"Invalid local artifact bundle ({type(exc).__name__})") from exc
