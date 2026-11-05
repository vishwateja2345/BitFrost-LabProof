"""Pure artifact tests using invented observations, not runtime acceptance proof."""
from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from labproof.adapters import parse_observation
from labproof.contracts import ValidationError, canonical
from labproof.local_report import LOCAL_LIMITATIONS, build_local_report
from labproof.sandbox.policy import SandboxLimits, reviewed_policy_bindings
from labproof.local_profiles import VARIANTS, build_launch_plan, default_profile
from labproof.verify_local import verify_local

DIGEST = "a" * 64
STAMP = "2026-11-01T00:00:00+00:00"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def rehash(root):
    manifest = json.loads((root / "manifest.json").read_bytes())
    manifest["artifacts"] = [{"path": p.relative_to(root).as_posix(), "bytes": len(p.read_bytes()),
                              "sha256": sha256(p.read_bytes()).hexdigest()}
                             for p in sorted(root.rglob("*")) if p.is_file() and p.name != "manifest.json"]
    write_json(root / "manifest.json", manifest)


def make_run(root, *, status="completed", count=8, accepted=True, pack="python"):
    root.mkdir()
    operation = {"python": "python-invariants", "typescript": "typescript-node-test", "c": "c-gcc", "rust": "rust-cargo-test"}[pack]
    tool = {"python": "unittest", "typescript": "node:test", "c": "gcc", "rust": "cargo"}[pack]
    config = {"schema_version": "local-config-1", "pack_id": pack, "fixture_id": f"{pack}-synthetic-v1",
              "operation_id": operation, "image_id": "sha256:" + DIGEST,
              "fixture_sha256": DIGEST, "worker_sha256": DIGEST,
              "limits": asdict(SandboxLimits()), "policy_version": "local-policy-1"}
    if pack == "rust":
        config["limits"] = asdict(SandboxLimits(wall_seconds=60, memory_bytes=536870912,
                                              scratch_bytes=67108864, output_executable=True))
    write_json(root / "config.json", config)
    profile = default_profile(pack)
    plans = [build_launch_plan({'schema_version': '1.0', 'pack_id': pack, 'operation_id': operation,
             'fixture_id': profile.fixture_id, 'parameters': {'variant': variant}}, config['image_id'])
             for variant in VARIANTS]
    policies = list(reviewed_policy_bindings(plans, profile.limits)[0])
    observations = {"uid": 65532, "gid": 65532, "root_write_denied": True, "fresh": True,
                    "cap_eff": "0000000000000000", "cap_bnd": "0000000000000000", "nnp": "1",
                    "interfaces": ["lo"], "socket_absent": True, "memory": str(config["limits"]["memory_bytes"]),
                    "swap": "0", "pids": str(config["limits"]["pids"]), "tmp_type": "tmpfs", "env": {},
                    "cpu": "100000 100000", "tmp_options": ["noexec", "nosuid", "nodev"],
                    "tmp_bytes": config["limits"]["scratch_bytes"]}
    if pack in ("c", "rust"):
        observations.update(network_none=True, tmp_noexec=True)
    if pack == "rust":
        observations.update(output_fresh=True, output_exec=True, scratch_noexec=True,
                            output_type="tmpfs", scratch_type="tmpfs", output_options=["rw", "nosuid", "nodev"],
                            scratch_options=["rw", "noexec", "nosuid", "nodev"],
                            output_bytes=config["limits"]["scratch_bytes"], scratch_bytes=config["limits"]["scratch_bytes"])
        observations["env"] = {"RUST_VERSION": "1.90.0", "CARGO_NET_OFFLINE": "true", "CARGO_HOME": "/usr/local/cargo",
                               "RUSTUP_HOME": "/usr/local/rustup", "PWD": "/tmp"}
    acceptance_report = {"runtime_id": DIGEST, "image_id": config["image_id"], "policy_digests": policies,
                         "canaries": [{"worker": f"canary_{i}", "observations": observations} for i in range(2)],
                         "timeout_cleanup": True, "output_bounded": True,
                         "timeout_check": {"container_id": "timeout_worker", "policy_digest": "b" * 64,
                                           "elapsed_seconds": 2.1, "cleanup_ok": True, "timed_out": True},
                         "output_check": {"container_id": "output_worker", "policy_digest": "c" * 64,
                                          "elapsed_seconds": 0.5, "cleanup_ok": True, "truncated": True,
                                          "output_bytes": config["limits"]["output_bytes"]},
                         "limitations": ["Invented unit-test data, not runtime acceptance evidence."]}
    write_json(root / "acceptance.json", {"accepted": accepted, "report": acceptance_report if accepted else None})
    records, executions = [], []
    slots = [(p, v) for p in ("observation", "verification") for v in ("alpha", "beta", "gamma", "delta")]
    for n, (phase, variant) in enumerate(slots[:count]):
        responses = [{"status": 403, "body": {"error": "forbidden"}},
                     {"status": 200, "body": {"id": "record-bob", "owner": "bob", "value": "SYNTHETIC-BOB"}},
                     {"status": 200, "body": {"id": "record-alice", "owner": "alice", "value": "SYNTHETIC-ALICE"}},
                     {"status": 401, "body": {"error": "unauthorized"}},
                     {"status": 404, "body": {"error": "not_found"}}]
        worker = {"schema_version": "worker-observation-1", "operation_id": operation,
                  "variant": variant, "tool": tool, "tool_version": "3.12.0", "status": "completed",
                  "exit_code": 0, "timed_out": False, "truncated": False,
                  "observations": [{"case_id": f"case-{i:02}", "response": r} for i, r in enumerate(responses, 1)]}
        if pack == "typescript":
            lines = ["TAP version 13"]
            for i, row in enumerate(worker.pop("observations"), 1):
                lines.extend([f"# Subtest: case-{i:02}", f"ok {i} - case-{i:02}", "# " + json.dumps(row)])
            lines.extend(["1..5", "# tests 5", "# suites 0", "# pass 5", "# fail 0", "# cancelled 0",
                          "# skipped 0", "# todo 0", "# duration_ms 1"])
            worker.update(stdout="\n".join(lines) + "\n", stderr="")
        raw = canonical(worker)
        record = {"phase": phase, "execution_id": f"exec_{n}", "reset_id": f"reset_{n}",
                  "observation": parse_observation(raw, operation, variant)}
        record["id"] = "ev_" + sha256(canonical(record)).hexdigest()[:24]
        records.append(record)
        write_json(root / "evidence" / f"{record['id']}.json", record)
        path = root / "outputs" / f"exec_{n}.txt"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
        executions.append({"execution_id": f"exec_{n}", "reset_id": f"reset_{n}", "phase": phase, "variant": variant,
                           "operation_id": operation, "image_id": config["image_id"], "policy_digest": policies[n % 4],
                           "runtime_id": DIGEST, "returncode": 0, "timed_out": False, "cancelled": False,
                           "truncated": False, "cleanup_ok": True, "elapsed_seconds": 0.1,
                           "output_bytes": len(raw), "raw_sha256": sha256(raw).hexdigest(), "evidence_id": record["id"]})
    write_json(root / "executions.json", executions)
    errors = [] if status == "completed" else [{"id": "error_1", "type": "stopped", "message": "Synthetic test stopped."}]
    (root / "errors.jsonl").write_bytes(b"".join(canonical(e) for e in errors))
    events = [("run_started", {"mode": "local", "pack_id": pack}), ("containment_checked", {"accepted": accepted})]
    events += [("execution_finished", {"execution_id": e["execution_id"], "evidence_id": e["evidence_id"]}) for e in executions]
    events += [("run_error", {"error_id": e["id"]}) for e in errors]
    events += [("run_completed" if status == "completed" else "run_stopped", {"status": status, "evidence_count": len(records)})]
    (root / "events.jsonl").write_bytes(b"".join(canonical({"sequence": i, "type": kind, "run_id": "local_test",
                                                           "timestamp": STAMP, "data": data}) for i, (kind, data) in enumerate(events, 1)))
    write_json(root / "report.json", build_local_report("local_test", status, pack, records, executions))
    write_json(root / "manifest.json", {"schema_version": "1.0", "project_id": "labproof", "run_id": "local_test",
                                       "mode": "local", "status": status, "created_at": STAMP,
                                       "artifacts": [], "limitations": LOCAL_LIMITATIONS})
    rehash(root)
    return root


def mutate_json(root, relative, mutate):
    path = root / relative
    value = json.loads(path.read_bytes())
    mutate(value)
    write_json(path, value)
    rehash(root)


@pytest.mark.parametrize("pack", ["python", "typescript", "c", "rust"])
def test_complete_is_consistent_not_authenticated(tmp_path, pack):
    result = verify_local(make_run(tmp_path / "run", pack=pack))
    assert result["valid"] and result["complete"]
    assert "not authenticity" in result["limitation"]


@pytest.mark.parametrize("status,count,accepted", [("incomplete", 3, True), ("blocked", 0, False), ("cancelled", 0, True)])
def test_partial_runs_remain_partial(tmp_path, status, count, accepted):
    result = verify_local(make_run(tmp_path / "run", status=status, count=count, accepted=accepted))
    assert result["valid"] and not result["complete"] and result["status"] == status


@pytest.mark.parametrize("field,value", [("summary", "Production vulnerabilities confirmed"), ("title", "Live assessment"),
                                         ("limitations", []), ("findings", []), ("public_remediation_claims", ["safe"])])
def test_rehashed_report_forgery_rejected(tmp_path, field, value):
    root = make_run(tmp_path / "run")
    mutate_json(root, "report.json", lambda report: report.update({field: value}))
    with pytest.raises(ValidationError):
        verify_local(root)


@pytest.mark.parametrize("field,value", [("reset_id", "reset_1"), ("phase", "verification"), ("operation_id", "c-gcc"),
                                         ("timed_out", True), ("truncated", True), ("cleanup_ok", False),
                                         ("returncode", True), ("output_bytes", 99999999), ("elapsed_seconds", 10**1000),
                                         ("raw_sha256", "b" * 64), ("evidence_id", None)])
def test_execution_tampering_rejected(tmp_path, field, value):
    root = make_run(tmp_path / "run")
    mutate_json(root, "executions.json", lambda executions: executions[0].update({field: value}))
    with pytest.raises(ValidationError):
        verify_local(root)


def test_rehashed_raw_output_rejected(tmp_path):
    root = make_run(tmp_path / "run")
    (root / "outputs" / "exec_0.txt").write_bytes(b"invented replacement")
    rehash(root)
    with pytest.raises(ValidationError):
        verify_local(root)


def test_event_order_and_identity_rejected(tmp_path):
    root = make_run(tmp_path / "run")
    events = (root / "events.jsonl").read_bytes().splitlines()
    events[1], events[2] = events[2], events[1]
    (root / "events.jsonl").write_bytes(b"\n".join(events) + b"\n")
    rehash(root)
    with pytest.raises(ValidationError):
        verify_local(root)


def test_execution_without_acceptance_rejected(tmp_path):
    root = make_run(tmp_path / "run")
    mutate_json(root, "acceptance.json", lambda acceptance: acceptance.update(accepted=False))
    with pytest.raises(ValidationError):
        verify_local(root)


def test_completed_missing_execution_rejected(tmp_path):
    root = make_run(tmp_path / "run", count=7)
    with pytest.raises(ValidationError):
        verify_local(root)


def test_unreferenced_registered_payload_rejected(tmp_path):
    root = make_run(tmp_path / "run")
    (root / "extra.txt").write_bytes(b"unexpected")
    rehash(root)
    with pytest.raises(ValidationError):
        verify_local(root)


@pytest.mark.parametrize("unsafe", ["../escape", "/absolute", "C:escape", "outputs/../escape", "outputs\\escape", "NUL"])
def test_manifest_paths_rejected(tmp_path, unsafe):
    root = make_run(tmp_path / "run")
    manifest = json.loads((root / "manifest.json").read_bytes())
    manifest["artifacts"][0]["path"] = unsafe
    write_json(root / "manifest.json", manifest)
    with pytest.raises(ValidationError):
        verify_local(root)


def test_malformed_json_is_controlled(tmp_path):
    root = make_run(tmp_path / "run")
    (root / "executions.json").write_bytes(b"[" * 20000 + b"0" + b"]" * 20000)
    rehash(root)
    with pytest.raises(ValidationError):
        verify_local(root)


def test_rehashed_unreviewed_policy_and_limits_are_rejected(tmp_path):
    root = make_run(tmp_path / 'run')
    mutate_json(root, 'acceptance.json', lambda a: a['report']['policy_digests'].__setitem__(0, 'f' * 64))
    with pytest.raises(ValidationError, match='trusted launch policies'):
        verify_local(root)
    root = make_run(tmp_path / 'other')
    mutate_json(root, 'config.json', lambda c: c['limits'].update(wall_seconds=45))
    with pytest.raises(ValidationError, match='reviewed local profile'):
        verify_local(root)


@pytest.mark.parametrize("field,value", [("runtime_id", "b" * 64), ("image_id", "sha256:" + "b" * 64),
                                         ("policy_digests", [DIGEST] * 4), ("timeout_cleanup", False),
                                         ("output_bounded", False), ("canaries", []), ("limitations", [])])
def test_retained_acceptance_consistency(tmp_path, field, value):
    root = make_run(tmp_path / "run")
    mutate_json(root, "acceptance.json", lambda a: a["report"].update({field: value}))
    with pytest.raises(ValidationError):
        verify_local(root)


@pytest.mark.parametrize("field,value", [("uid", 0), ("fresh", False), ("root_write_denied", False),
                                         ("cpu", "max 100000"), ("tmp_bytes", True), ("env", {"SECRET": "leaked"})])
def test_retained_canary_consistency(tmp_path, field, value):
    root = make_run(tmp_path / "run")
    mutate_json(root, "acceptance.json", lambda a: a["report"]["canaries"][0]["observations"].update({field: value}))
    with pytest.raises(ValidationError):
        verify_local(root)


@pytest.mark.parametrize("parse_failure", [True, False])
def test_failed_outputs_retained_without_becoming_evidence(tmp_path, parse_failure):
    root = make_run(tmp_path / "run", status="incomplete", count=1)
    executions = json.loads((root / "executions.json").read_bytes())
    execution = executions[0]
    (root / "evidence" / f"{execution['evidence_id']}.json").unlink()
    execution["evidence_id"] = None
    if parse_failure:
        raw = b"not a valid worker observation"
        (root / "outputs" / "exec_0.txt").write_bytes(raw)
        execution.update(output_bytes=len(raw), raw_sha256=sha256(raw).hexdigest())
    else:
        execution["returncode"] = 1
    write_json(root / "executions.json", executions)
    write_json(root / "report.json", build_local_report("local_test", "incomplete", "python", [], executions))
    events = [json.loads(row) for row in (root / "events.jsonl").read_bytes().splitlines()]
    events[2]["data"]["evidence_id"] = None
    events[-1]["data"]["evidence_count"] = 0
    (root / "events.jsonl").write_bytes(b"".join(canonical(e) for e in events))
    rehash(root)
    result = verify_local(root)
    assert result["valid"] and not result["complete"]


@pytest.mark.parametrize("check,field,value", [
    ("timeout_check", "timed_out", False), ("timeout_check", "cleanup_ok", False),
    ("timeout_check", "container_id", "canary_0"), ("timeout_check", "elapsed_seconds", 10**1000),
    ("output_check", "truncated", False), ("output_check", "output_bytes", True),
    ("output_check", "output_bytes", 1), ("output_check", "policy_digest", "b" * 64)])
def test_retained_lifecycle_details_consistent(tmp_path, check, field, value):
    root = make_run(tmp_path / "run")
    mutate_json(root, "acceptance.json", lambda a: a["report"][check].update({field: value}))
    with pytest.raises(ValidationError):
        verify_local(root)


@pytest.mark.parametrize("pack", ["python", "typescript"])
def test_legacy_nonexecutable_limit_shape_accepted(tmp_path, pack):
    root = make_run(tmp_path / "run", pack=pack)
    mutate_json(root, "config.json", lambda c: c["limits"].pop("output_executable"))
    assert verify_local(root)["complete"]


@pytest.mark.parametrize("pack,value", [("python", True), ("typescript", True), ("c", True),
                                        ("rust", False), ("rust", 1), ("rust", "true")])
def test_pack_executable_scope_rejected(tmp_path, pack, value):
    root = make_run(tmp_path / "run", pack=pack)
    mutate_json(root, "config.json", lambda c: c["limits"].update(output_executable=value))
    with pytest.raises(ValidationError):
        verify_local(root)


@pytest.mark.parametrize("field,value", [("network_none", False), ("tmp_noexec", False), ("output_fresh", False),
    ("output_exec", False), ("scratch_noexec", False), ("output_type", "ext4"), ("scratch_type", "ext4"),
    ("output_options", ["noexec", "nosuid", "nodev"]), ("output_options", ["rw", "nodev"]),
    ("scratch_options", ["nosuid", "nodev"]), ("output_bytes", True), ("scratch_bytes", 0),
    ("output_bytes", 67108865), ("env", {"CARGO_NET_OFFLINE": "false"})])
def test_rust_retained_tested_mount_controls(tmp_path, field, value):
    root = make_run(tmp_path / "run", pack="rust")
    mutate_json(root, "acceptance.json", lambda a: a["report"]["canaries"][0]["observations"].update({field: value}))
    with pytest.raises(ValidationError):
        verify_local(root)


@pytest.mark.parametrize("pack", ["c", "rust"])
def test_native_canary_fields_required(tmp_path, pack):
    root = make_run(tmp_path / "run", pack=pack)
    mutate_json(root, "acceptance.json", lambda a: a["report"]["canaries"][0]["observations"].pop("network_none"))
    with pytest.raises(ValidationError):
        verify_local(root)


@pytest.mark.parametrize("value", ["a" * 40, "  " + "aB" * 20 + "   " + "F" * 40 + " ",
                                  "\t " + "a" * 40 + "\t\t" + "b" * 40 + " \t"])
def test_official_gcc_signing_key_environment_accepted(tmp_path, value):
    root = make_run(tmp_path / "run", pack="c")
    mutate_json(root, "acceptance.json", lambda a: a["report"]["canaries"][0]["observations"]["env"].update(GPG_KEYS=value))
    assert verify_local(root)["complete"]


@pytest.mark.parametrize("value", ["", "   ", "a" * 39, "g" * 40, "a" * 40 + "\r" + "b" * 40,
                                  "a" * 40 + "\v" + "b" * 40, "a" * 40 + " " + "b" * 40,
                                  "a" * 40 + "\n", " ".join(["a" * 40] * 33), " " * 2049 + "a" * 40])
def test_invalid_gcc_signing_key_environment_rejected(tmp_path, value):
    root = make_run(tmp_path / "run", pack="c")
    mutate_json(root, "acceptance.json", lambda a: a["report"]["canaries"][0]["observations"]["env"].update(GPG_KEYS=value))
    with pytest.raises(ValidationError):
        verify_local(root)


def test_dispatch_accepts_local_artifacts_without_runtime(tmp_path, monkeypatch):
    from labproof.verify_artifacts import verify_artifacts
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("Verifier tried to execute a subprocess"))
    assert verify_artifacts(make_run(tmp_path / "run"))["complete"]
