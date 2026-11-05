"""Invented v2 artifacts/mocked sessions are not runtime acceptance evidence."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from labproof import local_engine
from labproof.cli import main
from labproof.contracts import ValidationError, canonical
from labproof.local_experiments import config_for, build_report, execution_record
from labproof.local_profiles import (default_experiment_plan, validate_experiment_plan,
                                     canonical_request_key, build_launch_plan, VARIANTS)
from labproof.packs import PackError
from labproof.sandbox import runtime
from labproof.sandbox.policy import policy_fingerprint
from labproof.verify_artifacts import verify_artifacts
from test_local_artifacts import make_run, rehash, mutate_json


def provision():
    return {"schema_version": "local-provisioning-2", "image_id": "sha256:" + "a" * 64,
            "base_digest": "python@sha256:" + "b" * 64,
            "source_sha256": "c" * 64, "oracle_sha256": "d" * 64,
            "worker_sha256": "e" * 64, "adapter_sha256": "f" * 64,
            "dependency_lock_sha256": None, "compiler_version": None,
            "compiler_flags": None, "binary_sha256": None}


def mock_session(tmp_path, monkeypatch, *, failure=None):
    # Reuse independently validated legacy mock canaries and worker bytes.
    legacy = make_run(tmp_path / "invented-legacy")
    accepted = json.loads((legacy / "acceptance.json").read_bytes())["report"]
    plan = default_experiment_plan("python")
    profile = validate_experiment_plan(plan)
    plans = [build_launch_plan({"schema_version": "1.0", "pack_id": "python", "operation_id": "python-invariants",
                              "fixture_id": "python-synthetic-v1", "parameters": {"variant": v}}, provision()["image_id"]) for v in VARIANTS]
    policies = [policy_fingerprint(p, profile.local.limits) for p in plans]
    accepted["policy_digests"] = policies
    raw_by_variant = {v: (legacy / "outputs" / f"exec_{i}.txt").read_bytes() for i, v in enumerate(VARIANTS)}

    class Session:
        def __init__(self, *args, **kwargs):
            self.n = 0

        def accept(self):
            return accepted

        def execute(self, operation):
            n = self.n
            self.n += 1
            if failure == "raise":
                raise RuntimeError("private diagnostics")
            variant = operation.rsplit("-", 1)[-1]
            raw = b"unrecognized" if failure == "parse" else raw_by_variant[variant]
            if failure == "exposed" and variant == "alpha":
                value = json.loads(raw)
                value["observations"][0]["response"] = value["observations"][1]["response"]
                raw = canonical(value)
            if failure == "ambiguous" and variant == "alpha":
                value = json.loads(raw)
                value["observations"][0]["response"] = {"status": 500, "body": {"error": "unknown"}}
                raw = canonical(value)
            return SimpleNamespace(execution_id=f"exec_{n}", container_id=f"worker_{n}", reset_id=f"reset_{n}",
                image_id=provision()["image_id"], policy_digest=policies[VARIANTS.index(variant)], runtime_id=accepted["runtime_id"],
                output=raw, returncode=1 if failure == "exit" else 0,
                timed_out=False, cancelled=False, truncated=failure == "truncated", cleanup_ok=True, elapsed_seconds=0.1)

    monkeypatch.setattr(local_engine, "provisioned_experiment", lambda _: provision())
    monkeypatch.setattr(runtime, "LiveSandboxSession", Session)
    return plan


@pytest.mark.parametrize("controller_name", ["windows", "linux"])
def test_offline_verification_accepts_reviewed_producer_not_reader_os(tmp_path, monkeypatch, controller_name):
    from labproof.sandbox import policy
    executable, endpoint, environment = policy.REVIEWED_CONTROLLERS[controller_name]
    with monkeypatch.context() as producer:
        producer.setattr(policy, "DOCKER_EXECUTABLE", executable)
        producer.setattr(policy, "DOCKER_ENDPOINT", endpoint)
        producer.setattr(policy, "REVIEWED_ENVIRONMENT", environment)
        plan = mock_session(tmp_path, producer)
        target = tmp_path / "cross-platform"
        local_engine.run_experiments(target, plan)
    assert verify_artifacts(target)["complete"]


def test_mixed_controller_policy_bindings_rejected(tmp_path, monkeypatch):
    from labproof.sandbox.policy import reviewed_policy_bindings
    plan = mock_session(tmp_path, monkeypatch)
    target = tmp_path / "mixed-controller"
    local_engine.run_experiments(target, plan)
    profile = validate_experiment_plan(plan)
    plans = [build_launch_plan({"schema_version": "1.0", "pack_id": "python",
        "operation_id": "python-invariants", "fixture_id": "python-synthetic-v1",
        "parameters": {"variant": variant}}, provision()["image_id"]) for variant in VARIANTS]
    windows, linux = reviewed_policy_bindings(plans, profile.local.limits)
    mutate_json(target, "acceptance.json", lambda value: value["report"].update(
        policy_digests=[windows[0], *linux[1:]]))
    rehash(target)
    with pytest.raises(ValidationError, match="trusted launch policies"):
        verify_artifacts(target)


def test_checkpoint_written_before_worker_launch(tmp_path, monkeypatch):
    plan = mock_session(tmp_path, monkeypatch)
    target = tmp_path / "durable"
    original = runtime.LiveSandboxSession.execute
    def execute(session, operation):
        rows = [json.loads(line) for line in (target / "checkpoints.jsonl").read_bytes().splitlines()]
        assert rows[-1]["kind"] == "attempted"
        assert rows[-1]["data"]["execution_id"] is None
        return original(session, operation)
    monkeypatch.setattr(runtime.LiveSandboxSession, "execute", execute)
    local_engine.run_experiments(target, plan)
    assert verify_artifacts(target)["complete"]
    rows = [json.loads(line) for line in (target / "checkpoints.jsonl").read_bytes().splitlines()]
    assert rows[-1] == {"kind": "finished", "data": {"status": "completed"}}


def test_process_exit_keeps_unfinished_attempt_journal(tmp_path, monkeypatch):
    plan = mock_session(tmp_path, monkeypatch)
    target = tmp_path / "interrupted"
    def exit_process(*args):
        raise SystemExit(9)
    monkeypatch.setattr(runtime.LiveSandboxSession, "execute", exit_process)
    with pytest.raises(SystemExit):
        local_engine.run_experiments(target, plan)
    assert not (target / "manifest.json").exists()
    rows = [json.loads(line) for line in (target / "checkpoints.jsonl").read_bytes().splitlines()]
    assert rows[-1]["kind"] == "attempted"
    assert not any(row["kind"] == "finished" for row in rows)


def test_altered_checkpoint_rejected_even_with_rehashed_manifest(tmp_path, monkeypatch):
    plan = mock_session(tmp_path, monkeypatch)
    target = tmp_path / "tampered-journal"
    local_engine.run_experiments(target, plan)
    path = target / "checkpoints.jsonl"
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    rows[3]["data"]["execution_id"] = "invented"
    path.write_bytes(b"".join(canonical(row) for row in rows))
    rehash(target)
    with pytest.raises(ValidationError, match="checkpoint"):
        verify_artifacts(target)


def test_unprovisioned_v2_is_verifiable_blocked_without_runtime(tmp_path, monkeypatch):
    def unavailable(_):
        raise FileNotFoundError("v2 not provisioned")
    monkeypatch.setattr(local_engine, "provisioned_experiment", unavailable)
    monkeypatch.setattr(runtime, "LiveSandboxSession", lambda *a, **k: pytest.fail("must not launch"))
    target = tmp_path / "blocked"
    assert local_engine.run_experiments(target, default_experiment_plan("python"))["status"] == "blocked"
    result = verify_artifacts(target)
    assert result["valid"] and not result["complete"]
    report = json.loads((target / "report.json").read_bytes())
    assert report["schema_version"] == "local-report-2"
    assert report["usage"]["target_invocations"] is None
    assert report["usage"]["tool_attempts"] == 0
    assert report["provenance"]["provisioning"] is None


def test_six_step_profile_completion_not_universal_eight(tmp_path, monkeypatch):
    plan = mock_session(tmp_path, monkeypatch)
    target = tmp_path / "six"
    assert local_engine.run_experiments(target, plan)["status"] == "completed"
    assert verify_artifacts(target)["complete"]
    report = json.loads((target / "report.json").read_bytes())
    assert len(report["experiments"]) == 6 and report["usage"]["replays"] == 3
    assert report["completion"]["missing_controls"] == []
    assert all(f["status"] != "confirmed" for f in report["findings"])
    assert report["usage"]["target_invocations"] is None
    assert report["usage"]["rejections"] is None and report["usage"]["shrinks"] is None


@pytest.mark.parametrize("failure,parse_status", [("exit", "unavailable"), ("truncated", "unavailable"), ("parse", "unrecognized"), ("raise", None)])
def test_failed_observations_and_unreturned_attempts(tmp_path, monkeypatch, failure, parse_status):
    plan = mock_session(tmp_path, monkeypatch, failure=failure)
    target = tmp_path / "failure"
    assert local_engine.run_experiments(target, plan)["status"] == "incomplete"
    assert not verify_artifacts(target)["complete"]
    report = json.loads((target / "report.json").read_bytes())
    assert report["usage"]["tool_attempts"] == 1
    if failure == "raise":
        assert report["usage"]["unreturned_attempts"] == 1
        assert report["usage"]["elapsed_seconds"] is None
    else:
        execution = report["experiments"][0]
        assert execution["parse_status"] == parse_status
        assert execution["evidence_id"] is None
        if failure == "exit":
            assert execution["controller_status"] == "completed" and execution["child_returncode"] == 1
    assert not report["evidence"] and all(f["status"] != "confirmed" for f in report["findings"])


@pytest.mark.parametrize("budget", ["actions", "wall_seconds", "output_bytes"])
def test_budgets_stop_before_action(tmp_path, monkeypatch, budget):
    plan = mock_session(tmp_path, monkeypatch)
    plan["budgets"][budget] = 0
    target = tmp_path / "budget"
    assert local_engine.run_experiments(target, plan)["status"] == "incomplete"
    assert verify_artifacts(target)["valid"]
    assert json.loads((target / "attempts.json").read_bytes()) == []


def test_missing_controls_cannot_complete(tmp_path, monkeypatch):
    plan = mock_session(tmp_path, monkeypatch)
    plan["steps"] = plan["steps"][:1]
    target = tmp_path / "controls"
    assert local_engine.run_experiments(target, plan)["status"] == "incomplete"
    assert verify_artifacts(target)["valid"]


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version="experiment-plan-9"),
    lambda p: p.update(image="sha256:" + "a" * 64),
    lambda p: p.update(command=["sh"]),
    lambda p: p["steps"][0]["request"].update(fixture_id="unreviewed"),
    lambda p: p["steps"][0]["request"].update(operation_id="python-hypothesis"),
    lambda p: p["steps"][0]["request"]["parameters"].update(seed=1),
    lambda p: p["steps"][3].update(replay_of="observation_beta"),
    lambda p: p["steps"][3].update(replay_of="verification_gamma"),
    lambda p: p["steps"][0].update(replay_of="observation_alpha"),
    lambda p: p["steps"].append(deepcopy(p["steps"][0])),
    lambda p: p["budgets"].update(actions=True),
    lambda p: p["budgets"].update(output_bytes=999999999),
])
def test_imported_plan_negatives(tmp_path, monkeypatch, mutation):
    plan = default_experiment_plan("python")
    mutation(plan)
    monkeypatch.setattr(runtime, "LiveSandboxSession", lambda *a, **k: pytest.fail("invalid plan launched"))
    with pytest.raises((ValidationError, PackError)):
        local_engine.run_experiments(tmp_path / "invalid", plan)
    assert not (tmp_path / "invalid").exists()


def test_full_request_seed_fixture_and_phase_identity():
    request = {"schema_version": "1.0", "pack_id": "python", "operation_id": "python-hypothesis", "fixture_id": "python-synthetic-v1",
               "parameters": {"variant": "alpha", "seed": 1, "cases": 20}}
    one = canonical_request_key(request, "observation")
    assert canonical_request_key(request, "verification") != one
    request["parameters"]["seed"] = 2
    assert canonical_request_key(request, "observation") != one
    request["parameters"]["seed"] = 1
    request["parameters"]["cases"] = 21
    assert canonical_request_key(request, "observation") != one


@pytest.mark.parametrize("relative,mutation", [
    ("config.json", lambda c: c.update(schema_version="local-config-1")),
    ("config.json", lambda c: c.update(schema_version="local-config-3")),
    ("config.json", lambda c: c["provisioning"].update(source_sha256=c["provisioning"]["oracle_sha256"])),
    ("report.json", lambda r: r.update(schema_version="local-report-1")),
    ("report.json", lambda r: r["usage"].update(target_invocations=30)),
    ("report.json", lambda r: r["usage"].update(replays=99)),
    ("executions.json", lambda e: e[1].update(reset_id=e[0]["execution_id"])),
    ("executions.json", lambda e: e[1].update(container_id="canary_0")),
    ("executions.json", lambda e: e[0].update(request_key="a" * 64)),
    ("executions.json", lambda e: e[3].update(replay_of="observation_beta")),
    ("executions.json", lambda e: e[0].update(child_returncode=True)),
    ("executions.json", lambda e: e[0].update(controller_status="interrupted")),
    ("executions.json", lambda e: e[0].update(observation=None)),
    ("executions.json", lambda e: e[0].update(output_bytes=0)),
    ("attempts.json", lambda a: a.pop()),
    ("acceptance.json", lambda a: a["report"]["policy_digests"].__setitem__(0, "f" * 64)),
])
def test_rehashed_tampering_rejected(tmp_path, monkeypatch, relative, mutation):
    plan = mock_session(tmp_path, monkeypatch)
    target = tmp_path / "tamper"
    local_engine.run_experiments(target, plan)
    mutate_json(target, relative, mutation)
    with pytest.raises(ValidationError):
        verify_artifacts(target)


def test_cli_plan_and_bad_plan(tmp_path, capsys):
    assert main(["experiment-plan", "--pack", "python"]) == 0
    plan = json.loads(capsys.readouterr().out)
    validate_experiment_plan(plan)
    plan["command"] = "arbitrary"
    path = tmp_path / "plan.json"
    path.write_bytes(canonical(plan))
    assert main(["experiments", "--plan", str(path), "--output", str(tmp_path / "no")]) == 1
    assert not (tmp_path / "no").exists()


@pytest.mark.parametrize("failure,verdict", [("exposed", "confirmed"), ("ambiguous", "inconclusive")])
def test_host_verdict_requires_observation_and_controls(tmp_path, monkeypatch, failure, verdict):
    plan = mock_session(tmp_path, monkeypatch, failure=failure)
    target = tmp_path / "verdict"
    assert local_engine.run_experiments(target, plan)["status"] == "completed"
    assert verify_artifacts(target)["complete"]
    report = json.loads((target / "report.json").read_bytes())
    finding = next(f for f in report["findings"] if f["variant"] == "alpha")
    assert finding["status"] == verdict
    assert all(e["child_returncode"] == 0 for e in report["experiments"])
    if verdict == "confirmed":
        assert len(finding["evidence_ids"]) == 6


def test_missing_profile_control_blocks_exposed_observation(tmp_path, monkeypatch):
    plan = mock_session(tmp_path, monkeypatch, failure="exposed")
    plan["steps"] = [s for s in plan["steps"] if s["request"]["parameters"]["variant"] != "gamma"]
    target = tmp_path / "missing-control"
    assert local_engine.run_experiments(target, plan)["status"] == "incomplete"
    assert verify_artifacts(target)["valid"]
    report = json.loads((target / "report.json").read_bytes())
    assert all(f["status"] != "confirmed" for f in report["findings"])


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version="local-provisioning-1"),
    lambda p: p.update(fixture_sha256=p.pop("source_sha256")),
    lambda p: p.update(oracle_sha256=None),
    lambda p: p.update(image_id="python:latest"),
    lambda p: p.update(base_digest="python:latest"),
    lambda p: p.update(compiler_flags="arbitrary"),
    lambda p: p.update(adapter_sha256="missing"),
])
def test_provenance_requires_v2_source_oracle_split(mutation):
    value = provision()
    mutation(value)
    with pytest.raises(ValidationError):
        config_for(default_experiment_plan("python"), value)
