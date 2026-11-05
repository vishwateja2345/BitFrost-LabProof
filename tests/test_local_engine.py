"""Local orchestration failures use injected sessions, never actual workers."""
import json
from types import SimpleNamespace

import pytest

from labproof import local_engine
from labproof.cli import main
from labproof.sandbox import runtime


@pytest.fixture
def provision(monkeypatch):
    monkeypatch.setattr(local_engine, "provisioned_pack", lambda _: {
        "image_id": "sha256:" + "a" * 64, "base_digest": "python@sha256:" + "b" * 64,
        "fixture_sha256": "c" * 64, "worker_sha256": "d" * 64})


def test_missing_v1_provisioning_is_a_verified_blocked_run(tmp_path, monkeypatch):
    from labproof.verify_local import verify_local
    from labproof.sandbox import runtime

    def missing(_):
        raise FileNotFoundError('No reviewed local provisioning')

    monkeypatch.setattr(local_engine, 'provisioned_pack', missing)
    monkeypatch.setattr(runtime, 'LiveSandboxSession', lambda *args, **kwargs: pytest.fail('No worker without provisioning'))
    target = tmp_path / 'missing'
    assert local_engine.run_local(target, 'python')['status'] == 'blocked'
    assert verify_local(target)['valid'] is True
    assert json.loads((target / 'config.json').read_bytes())['image_id'] == 'sha256:' + '0' * 64


def test_acceptance_failure_retains_blocked_artifacts(tmp_path, monkeypatch, provision):
    class Session:
        def __init__(self, *args, **kwargs):
            pass

        def accept(self):
            raise RuntimeError("do-not-export-sensitive-error")

        def execute(self, *args):
            pytest.fail("Execution must not occur before acceptance")

    monkeypatch.setattr(runtime, "LiveSandboxSession", Session)
    target = tmp_path / "blocked"
    assert local_engine.run_local(target, "python")["status"] == "blocked"
    assert json.loads((target / "acceptance.json").read_text()) == {"accepted": False, "report": None}
    assert json.loads((target / "executions.json").read_text()) == []
    assert "do-not-export" not in (target / "errors.jsonl").read_text()
    report = json.loads((target / "report.json").read_text())
    assert not report["evidence"]
    assert all(f["status"] != "confirmed" for f in report["findings"])


def test_failed_worker_output_retained_without_evidence(tmp_path, monkeypatch, provision):
    class Session:
        def __init__(self, *args, **kwargs):
            pass

        def accept(self):
            return {"test_double": True}

        def execute(self, *args):
            return SimpleNamespace(execution_id="1" * 64, reset_id="1" * 64,
                image_id="sha256:" + "a" * 64, policy_digest="2" * 64, runtime_id="3" * 64,
                output=b"malformed-output", returncode=1, timed_out=False, cancelled=False,
                truncated=False, cleanup_ok=True, elapsed_seconds=0.1)

    monkeypatch.setattr(runtime, "LiveSandboxSession", Session)
    monkeypatch.setattr(local_engine, "parse_observation", lambda *args: pytest.fail(
        "Nonzero worker exit must fail before parsing, even if output could be accepted"))
    target = tmp_path / "partial"
    assert local_engine.run_local(target, "python")["status"] == "incomplete"
    executions = json.loads((target / "executions.json").read_text())
    assert len(executions) == 1 and executions[0]["evidence_id"] is None
    assert (target / "outputs" / ("1" * 64 + ".txt")).read_bytes() == b"malformed-output"
    assert not list((target / "evidence").iterdir())
    events = [json.loads(line) for line in (target / "events.jsonl").read_text().splitlines()]
    assert [e["type"] for e in events] == ["run_started", "containment_checked", "execution_finished", "run_error", "run_stopped"]


def test_cli_requires_explicit_local_arguments(capsys):
    assert main(["assess", "--mode", "local"]) == 1
    assert "requires --pack and --output" in capsys.readouterr().err


def test_existing_output_never_replaced(tmp_path, provision):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep").write_text("original")
    with pytest.raises(FileExistsError):
        local_engine.run_local(target, "python")
    assert (target / "keep").read_text() == "original"


@pytest.mark.parametrize("pack", ("python", "typescript", "c", "rust"))
def test_engine_uses_reviewed_profiles_without_changing_v1(tmp_path, monkeypatch, provision, pack):
    from dataclasses import asdict
    from labproof.local_profiles import default_profile
    from labproof.verify_local import verify_local

    profile = default_profile(pack)
    captured = []

    class Session:
        def __init__(self, plans, *, language, limits):
            captured.extend(plans)
            assert language == profile.language
            assert limits is profile.limits

        def accept(self):
            raise RuntimeError("No real workers in this test")

    monkeypatch.setattr(runtime, "LiveSandboxSession", Session)
    # The compatibility export must not be an alternate execution authority.
    monkeypatch.setattr(local_engine, "OPERATIONS", {})
    target = tmp_path / pack
    assert local_engine.run_local(target, pack)["status"] == "blocked"
    assert [(p.operation_id, p.argv) for p in captured] == [
        (f"{profile.operation_id}-{variant}",
         (profile.executable, *profile.prefix, profile.operation_id, variant))
        for variant in local_engine.VARIANTS]
    config = json.loads((target / "config.json").read_bytes())
    assert config["schema_version"] == "local-config-1"
    assert config["policy_version"] == "local-policy-1"
    assert config["limits"] == asdict(profile.limits)
    assert config["fixture_id"] == profile.fixture_id
    assert verify_local(target)["valid"]


@pytest.mark.parametrize("pack", (None, [], True, "python\n", "missing"))
def test_bad_pack_fails_before_worker_construction(tmp_path, monkeypatch, provision, pack):
    from labproof.packs import PackError

    def no_worker(*args, **kwargs):
        pytest.fail("Invalid pack reached worker construction")

    monkeypatch.setattr(runtime, "LiveSandboxSession", no_worker)
    target = tmp_path / "invalid"
    with pytest.raises(PackError):
        local_engine.run_local(target, pack)
    assert not target.exists()


@pytest.mark.parametrize("field,value", (("operation_id", "python-ast"),
                                         ("fixture_id", "python-second-fixture")))
def test_unmapped_pair_fails_before_worker_construction(tmp_path, monkeypatch, provision, field, value):
    from dataclasses import replace
    from labproof import local_profiles
    from labproof.packs import FixtureSpec, PackError, PackRegistry, REGISTRY

    pack = REGISTRY.get("python")
    monkeypatch.setattr(local_profiles, "REGISTRY", PackRegistry((replace(
        pack, fixtures=(*pack.fixtures, FixtureSpec("python-second-fixture"))),)))
    profile = replace(local_profiles.default_profile("python"), **{field: value})
    monkeypatch.setattr(local_engine, "default_profile", lambda _: profile)

    def no_worker(*args, **kwargs):
        pytest.fail("Unmapped pair reached worker construction")

    monkeypatch.setattr(runtime, "LiveSandboxSession", no_worker)
    target = tmp_path / "unmapped"
    with pytest.raises(PackError, match="No reviewed local operation/fixture"):
        local_engine.run_local(target, "python")
    assert not target.exists()
