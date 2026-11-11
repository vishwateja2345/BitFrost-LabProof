import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from hashlib import sha256

import pytest

from labproof.cli import main
from labproof.contracts import ValidationError, canonical, parse_json, safe_relative
from labproof.engine import run_demo
from labproof.policy import Action, Budget, Check, Limits, PolicyError
from labproof.report import adjudicate, classify
from labproof.transport import ReplayTransport, Response
from labproof.verify_artifacts import verify_artifacts


@pytest.fixture
def run(tmp_path):
    root = tmp_path / "run"
    run_demo(root)
    return root


def load(path):
    return json.loads(path.read_text())


def resign(root, relative, value=None):
    path = root / relative
    if value is not None:
        path.write_bytes(canonical(value))
    manifest = load(root / "manifest.json")
    raw = path.read_bytes()
    entry = next(a for a in manifest["artifacts"] if a["path"] == relative)
    entry.update(bytes=len(raw), sha256=sha256(raw).hexdigest())
    (root / "manifest.json").write_bytes(canonical(manifest))


def test_demo_no_network_or_shell(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External execution forbidden")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setenv("HTTP_PROXY", "http://invalid.example")
    monkeypatch.setenv("HTTPS_PROXY", "http://invalid.example")
    root = tmp_path / "offline"
    assert main(["demo", "--output", str(root)]) == 0
    assert verify_artifacts(root)["complete"]
    report = load(root / "report.json")
    assert len(report["evidence"]) == 36
    assert [f["status"] for f in report["findings"]] == ["confirmed", "rejected", "inconclusive"] * 3
    assert report["public_remediation_claims"] == []
    assert report["usage"]["model_usage"] is None
    assert main(["doctor"]) == 2
    assert main(["assess"]) == 2


def test_refuses_overwrite(run):
    original = (run / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        run_demo(run)
    assert (run / "manifest.json").read_bytes() == original


@pytest.mark.parametrize("count", [0, 1, 12, 35])
def test_budget_incomplete_not_clean(tmp_path, count):
    root = tmp_path / "limited"
    manifest = run_demo(root, limits=Limits(max_actions=count))
    assert manifest["status"] == "incomplete"
    report = load(root / "report.json")
    assert not all(f["status"] == "rejected" for f in report["findings"])
    assert verify_artifacts(root)["complete"] is False
    if count == 0:
        assert all(f["status"] == "not_tested" for f in report["findings"])
    assert main(["verify-artifacts", str(root)]) == 2


def test_cancel_and_timeout(tmp_path):
    limits = Limits()
    budget = Budget(limits)
    budget.cancelled = True
    run_demo(tmp_path / "cancel", limits=limits, budget=budget)
    assert verify_artifacts(tmp_path / "cancel")["status"] == "cancelled"
    clock = iter([0, 11])
    budget = Budget(limits, clock=lambda: next(clock))
    run_demo(tmp_path / "timeout", limits=limits, budget=budget)
    assert verify_artifacts(tmp_path / "timeout")["status"] == "incomplete"


@pytest.mark.parametrize("limits", [Limits(max_response_bytes=1), Limits(max_total_bytes=1)])
def test_response_budget(tmp_path, limits):
    run_demo(tmp_path / "bytes", limits=limits)
    report = load(tmp_path / "bytes/report.json")
    assert report["usage"]["tool_attempts"] == 1
    assert report["evidence"] == []
    assert not verify_artifacts(tmp_path / "bytes")["complete"]


@pytest.mark.parametrize("overrides", [
    {"url": "http://127.0.0.1"}, {"Host": "metadata"}, {"method": "POST"},
    {"headers": {}}, {"variant": "vulnerable"}, {"expected": "confirmed"},
    {"actor_id": "admin"}, {"check_id": "shell"}, {"control": "override"},
    {"check_id": ["object_authorization"]},
])
def test_policy_rejects_extra_or_unknown(overrides):
    value = {"check_id": "object_authorization", "actor_id": "alice", "control": "probe", **overrides}
    with pytest.raises(PolicyError):
        Action.parse(value)


def test_no_gold_labels_in_tool_surface():
    action = Action.parse({"check_id": "html_reflection", "actor_id": "alice", "control": "probe"})
    assert set(action.to_dict()) == {"check_id", "actor_id", "control"}
    assert "variant" not in Response.__dataclass_fields__
    with pytest.raises(PolicyError):
        Action(Check.AUTHORIZATION, "bob", "probe").validate()


@pytest.mark.parametrize("kwargs", [{"max_actions": 37}, {"max_actions": True}, {"max_model_calls": 1}, {"max_seconds": float("nan")}, {"concurrency": 2}, {"max_total_bytes": -1}])
def test_limits_fail_closed(kwargs):
    with pytest.raises(PolicyError):
        Limits(**kwargs)


@pytest.mark.parametrize("seconds", [10**400, -(10**400), float("inf"), float("-inf"), float("nan"), True, 0, 10.01])
def test_wall_time_rejects_unbounded_values_without_overflow(seconds):
    with pytest.raises(PolicyError, match="Invalid wall-time limit"):
        Limits(max_seconds=seconds)


@pytest.mark.parametrize("seconds", [0.001, 1, 10, 10.0])
def test_wall_time_accepts_bounded_numbers(seconds):
    assert Limits(max_seconds=seconds).max_seconds == seconds


def test_rehashed_huge_wall_time_is_validation_error(run, capsys):
    config = load(run / "config.json")
    config["limits"]["max_seconds"] = 10**400
    resign(run, "config.json", config)
    with pytest.raises(ValidationError):
        verify_artifacts(run)
    assert main(["verify-artifacts", str(run)]) == 1
    assert "ValidationError" in capsys.readouterr().err


@pytest.mark.parametrize("damage", ["title", "summary", "counts", "limitations_empty", "limitations_removed", "limitations_contradictory"])
@pytest.mark.parametrize("max_actions", [0, 36])
def test_rehashed_replay_narrative_tampering(tmp_path, damage, max_actions):
    root = tmp_path / "narrative"
    run_demo(root, limits=Limits(max_actions=max_actions))
    report = load(root / "report.json")
    if damage == "title":
        report["title"] = "Verified live production security assessment"
    elif damage == "summary":
        report["summary"] = "Isolation verified; production systems are secure."
    elif damage == "counts":
        report["summary"] = report["summary"].replace("0 confirmed" if max_actions == 0 else "3 confirmed", "9 confirmed")
    elif damage == "limitations_empty":
        report["limitations"] = []
    elif damage == "limitations_removed":
        report["limitations"].pop()
    else:
        report["limitations"].append("All findings were measured on real production services.")
    # Update both copies and the digest so failure cannot be mere hash inconsistency.
    manifest = load(root / "manifest.json")
    manifest["limitations"] = report["limitations"]
    (root / "manifest.json").write_bytes(canonical(manifest))
    resign(root, "report.json", report)
    with pytest.raises(ValidationError, match="deterministic replay narrative"):
        verify_artifacts(root)


@pytest.mark.parametrize("max_actions", [0, 1, 35, 36])
def test_canonical_replay_narrative_verifies_without_modifying_artifacts(tmp_path, max_actions):
    root = tmp_path / "preserved"
    run_demo(root, limits=Limits(max_actions=max_actions))
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = verify_artifacts(root)
    assert result["complete"] == (max_actions == 36)
    report = load(root / "report.json")
    assert f"Synthetic replay ({result['status']})" in report["summary"]
    assert "Not a live security assessment." in report["summary"]
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("response", [
    {"status": 302, "content_type": "text/plain", "body": "redirect"},
    {"status": True, "content_type": "text/plain", "body": "x"},
    {"status": 200, "content_type": "text/plain", "body": 3},
    {"status": 200, "content_type": "text/plain", "body": "x" * 4097},
    {"status": 200, "content_type": "text/plain", "body": "x", "location": "http://example.org"},
])
def test_malformed_responses(response):
    with pytest.raises(ValidationError):
        Response.parse(response)


def test_crash_records_incomplete_without_exception_secrets(tmp_path):
    class Broken(ReplayTransport):
        def execute(self, *args, **kwargs):
            raise RuntimeError("SECRET-MUST-NOT-BE-EXPORTED")
    root = tmp_path / "broken"
    run_demo(root, transport=Broken())
    assert not verify_artifacts(root)["complete"]
    assert "SECRET-MUST-NOT" not in (root / "errors.jsonl").read_text()


def test_status_alone_does_not_confirm(run):
    evidence = load(run / "report.json")["evidence"]
    for e in evidence:
        if e["check_id"] == "object_authorization" and e["control"] == "probe":
            e["response"]["body"] = "{}"
    assert not any(f["status"] == "confirmed" for f in adjudicate(evidence) if f["check_id"] == "object_authorization")


def test_missing_controls_never_confirm(run):
    evidence = load(run / "report.json")["evidence"]
    for filter_fn in [lambda e: e["control"] != "normal", lambda e: e["phase"] != "verification", lambda e: e["variant"] != "corrected"]:
        assert not any(f["status"] == "confirmed" for f in adjudicate([e for e in evidence if filter_fn(e)]))
    assert all(f["status"] == "not_tested" for f in adjudicate([]))


def test_variant_name_cannot_force_confirmation(run):
    evidence = load(run / "report.json")["evidence"]
    for e in evidence:
        if e["variant"] == "vulnerable":
            counterpart = next(c for c in evidence if c["variant"] == "corrected" and all(c[k] == e[k] for k in ("check_id", "control", "phase")))
            e["response"] = counterpart["response"]
    assert all(f["status"] == "rejected" for f in adjudicate(evidence) if f["variant"] == "vulnerable")


def test_replay_reset():
    transport = ReplayTransport()
    transport._fixtures = {}
    transport.reset()
    response = transport.execute(Action(Check.REFLECTION, "alice", "probe"), variant="vulnerable", budget=Budget(Limits()))
    assert "<em>LABPROOF-MARKER</em>" in response.body
    assert "script" not in response.body


@pytest.mark.parametrize("path", ["../outside", "/absolute", "a//b", "a/./b", "C:/data", "a\\b", "a:b", "NUL.txt", "CON", "file.", "a/..", ""])
def test_unsafe_paths(path):
    with pytest.raises(ValidationError):
        safe_relative(path)


@pytest.mark.parametrize("damage", ["byte_change", "missing", "unregistered", "duplicate_path", "unsafe_path", "version", "extra_manifest", "negative_size"])
def test_manifest_and_digest_damage(run, damage):
    m = load(run / "manifest.json")
    if damage == "byte_change":
        with (run / "report.json").open("ab") as f:
            f.write(b" ")
    elif damage == "missing":
        (run / "report.json").unlink()
    elif damage == "unregistered":
        (run / "surprise.txt").write_text("unexpected")
    else:
        if damage == "duplicate_path":
            m["artifacts"].append(m["artifacts"][0])
        elif damage == "unsafe_path":
            m["artifacts"][0]["path"] = "../outside"
        elif damage == "version":
            m["schema_version"] = "2.0"
        elif damage == "extra_manifest":
            m["isolation_verified"] = True
        else:
            m["artifacts"][0]["bytes"] = -1
        (run / "manifest.json").write_bytes(canonical(m))
    with pytest.raises(ValidationError):
        verify_artifacts(run)


@pytest.mark.parametrize("damage", ["duplicate_id", "dangling_ref", "dangling_source", "claim_laundering", "changed_verdict", "missing_evidence", "changed_content", "changed_usage", "changed_provenance"])
def test_domain_damage_even_if_manifest_rehashed(run, damage):
    r = load(run / "report.json")
    if damage == "duplicate_id":
        r["evidence"].append(r["evidence"][0])
    elif damage == "dangling_ref":
        r["findings"][0]["evidence_ids"].append("ev_missing")
    elif damage == "dangling_source":
        r["evidence"][0]["fixture_sha256"] = "0" * 64
    elif damage == "claim_laundering":
        r["public_remediation_claims"] = [{"claim": "A public fix exists"}]
    elif damage == "changed_verdict":
        r["findings"][0]["status"] = "rejected"
    elif damage == "missing_evidence":
        r["evidence"] = []
    elif damage == "changed_content":
        r["evidence"][0]["content"] = "new content"
    elif damage == "changed_usage":
        r["usage"]["model_calls"] = 1
    else:
        r["provenance"]["observations"] = "live"
    resign(run, "report.json", r)
    with pytest.raises(ValidationError):
        verify_artifacts(run)


@pytest.mark.parametrize("damage", ["sequence", "completion", "wrong_run", "dangling_event", "missing_event", "duplicate_event", "changed_action", "time"])
def test_event_damage_even_if_manifest_rehashed(run, damage):
    events = [json.loads(row) for row in (run / "events.jsonl").read_text().splitlines()]
    if damage == "sequence":
        events[3]["sequence"] += 1
    elif damage == "completion":
        events.pop()
    elif damage == "wrong_run":
        events[2]["run_id"] = "wrong"
    elif damage == "dangling_event":
        next(e for e in events if e["type"] == "evidence_collected")["data"]["evidence_id"] = "missing"
    elif damage == "missing_event":
        events = [e for e in events if e["type"] != "evidence_collected"]
    elif damage == "duplicate_event":
        events.insert(4, dict(events[3]))
    elif damage == "changed_action":
        next(e for e in events if e["type"] == "action_selected")["data"]["variant"] = "corrected"
    else:
        events[3]["timestamp"] = "2000-01-01T00:00:00+00:00"
    if damage in {"missing_event", "duplicate_event"}:
        for seq, event in enumerate(events, 1):
            event["sequence"] = seq
    (run / "events.jsonl").write_bytes(b"".join(canonical(e) for e in events))
    resign(run, "events.jsonl")
    with pytest.raises(ValidationError):
        verify_artifacts(run)


def test_duplicate_json_and_nonfinite():
    for value in [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}', b'\xff']:
        with pytest.raises(ValidationError):
            parse_json(value)


def test_symlink_rejected(run, tmp_path):
    target = tmp_path / "external"
    target.write_text("x")
    try:
        (run / "link").symlink_to(target)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(ValidationError):
        verify_artifacts(run)


def test_optimized_python_rejects_corruption(run):
    (run / "events.jsonl").write_bytes(b"")
    resign(run, "events.jsonl")
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run([sys.executable, "-O", "-m", "labproof", "verify-artifacts", str(run)], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "ValidationError" in result.stderr


def test_root_envelope_matches_schema(run):
    # Optional independent schema conformance check, not a runtime dependency.
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).resolve().parents[1] / "docs/run-envelope.schema.json"
    if not schema_path.exists():
        pytest.skip("Run-envelope schema is not available")
    jsonschema.validate(load(run / "manifest.json"), load(schema_path), format_checker=jsonschema.FormatChecker())
