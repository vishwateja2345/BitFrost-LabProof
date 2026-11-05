"""Registry visibility does not imply executable sandbox readiness."""
import json

from labproof.cli import main


def test_packs_lists_unprovisioned_operations(capsys):
    assert main(["packs"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["assessment"] == "blocked"
    assert {p["pack_id"] for p in result["packs"]} == {"python", "typescript", "c", "rust"}
    for pack in result["packs"]:
        assert pack["provisioned"] is False
        assert pack["image_digest"] is None
        assert all(tool["maturity"] == "declared" for tool in pack["tools"])
    assert result["limitations"]
    assert result["local_mode"] == {"readiness": "not_probed", "fixed_operations": {
        "python": "python-invariants", "typescript": "typescript-node-test",
        "c": "c-gcc", "rust": "rust-cargo-test"}}


def test_assessment_still_fails_closed(capsys):
    assert main(["assess"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["assessment"] == "blocked"
    assert result["containment"] == "not_verified"


def test_doctor_describes_local_mode_without_probing(capsys, monkeypatch):
    import subprocess
    from labproof import local_engine

    def denied(*args, **kwargs):
        raise AssertionError("Metadata commands must not probe or execute")

    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(local_engine, "provisioned_pack", denied)
    assert main(["doctor"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["local_mode"]["implemented"] is True
    assert result["local_mode"]["readiness"] == "not_probed"
    assert result["assessment"] == "blocked"
    assert result["network_operations"] == 0
    assert main(["packs"]) == 0
