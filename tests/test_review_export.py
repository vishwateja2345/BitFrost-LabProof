"""Check authorization at the defensive export boundary."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Event

import pytest

from labproof import review_export
from labproof.cli import main
from labproof.contracts import ValidationError, canonical
from labproof.engine import run_demo


@pytest.fixture
def review(tmp_path):
    run = tmp_path / "source"
    run_demo(run)
    return {
        "root": run,
        "output": tmp_path / "review.json",
        "task": "evidence-review",
        "ledger": tmp_path / "approval.sqlite3",
        "key": bytes(range(32)),
    }


def test_cli_exports_once_across_separate_invocations(review, monkeypatch, capsys):
    monkeypatch.setenv(review_export.KEY_ENV, review["key"].hex())
    command = ["review-export", "--ledger", str(review["ledger"])]
    args = [str(review["root"]), "--task", review["task"], "--output", str(review["output"])]
    approval_path = review["output"].with_name("approval.json")
    assert main(command + ["approve", *args]) == 0
    approval_path.write_text(capsys.readouterr().out, encoding="utf-8")
    redeem = command + ["redeem", *args, "--approval", str(approval_path)]
    assert main(redeem) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["runs"] == 1
    bundle = json.loads(review["output"].read_bytes())
    assert bundle["runs"][0]["manifest"]["mode"] == "replay"

    # Remove the existing destination as a confounder for the replay assertion.
    review["output"].rename(review["output"].with_name("archived-review.json"))
    assert main(redeem) == 1
    assert "already used" in capsys.readouterr().err
    assert not review["output"].exists()


def test_rejects_different_task_destination_and_manifest(review):
    approval = review_export.approve_export(**review)
    with pytest.raises(ValidationError, match="different task"):
        review_export.redeem_export(**{**review, "task": "different"}, approval=approval)
    with pytest.raises(ValidationError, match="export destination"):
        review_export.redeem_export(**{**review, "output": review["output"].with_name("different.json")}, approval=approval)

    manifest_path = review["root"] / "manifest.json"
    original = manifest_path.read_bytes()
    manifest = json.loads(original)
    manifest["limitations"].append("Changed after approval")
    manifest_path.write_bytes(canonical(manifest))
    with pytest.raises(ValidationError, match="source manifest"):
        review_export.redeem_export(**review, approval=approval)
    assert not review["output"].exists()

    manifest_path.write_bytes(original)
    assert review_export.redeem_export(**review, approval=approval)["runs"] == 1


def test_rejects_tampering_expiry_and_revocation(review, monkeypatch):
    monkeypatch.setattr(review_export.time, "time", lambda: 100)
    approval = review_export.approve_export(**review, ttl=10)
    altered = deepcopy(approval)
    altered["claims"]["expires_at"] += 20
    with pytest.raises(ValidationError, match="signature"):
        review_export.redeem_export(**review, approval=altered)

    monkeypatch.setattr(review_export.time, "time", lambda: 110)
    with pytest.raises(ValidationError, match="expired"):
        review_export.redeem_export(**review, approval=approval)
    fresh = review_export.approve_export(**review)
    revoked = review_export.revoke_export(ledger=review["ledger"], key=review["key"], approval=fresh)
    assert revoked["status"] == "revoked"
    with pytest.raises(ValidationError, match="revoked"):
        review_export.redeem_export(**review, approval=fresh)
    assert not review["output"].exists()


def test_only_one_worker_can_start_the_same_export(review, monkeypatch):
    approval = review_export.approve_export(**review)
    entered, resume = Event(), Event()
    real_export = review_export.export_viewer

    def held_export(*args, **kwargs):
        entered.set()
        assert resume.wait(timeout=5)
        return real_export(*args, **kwargs)

    monkeypatch.setattr(review_export, "export_viewer", held_export)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(review_export.redeem_export, **review, approval=approval)
        try:
            assert entered.wait(timeout=5)
            assert not review["output"].exists()
            second = workers.submit(review_export.redeem_export, **review, approval=approval)
            with pytest.raises(ValidationError, match="already used"):
                second.result(timeout=5)
        finally:
            resume.set()
        assert first.result(timeout=5)["runs"] == 1


def test_export_failure_does_not_reopen_consumed_approval(review):
    approval = review_export.approve_export(**review)
    report = review["root"] / "report.json"
    original = report.read_bytes()
    report.write_bytes(original[:-1] + b" ")
    with pytest.raises(ValidationError, match="Digest mismatch"):
        review_export.redeem_export(**review, approval=approval)
    assert not review["output"].exists()
    report.write_bytes(original)
    with pytest.raises(ValidationError, match="already used"):
        review_export.redeem_export(**review, approval=approval)


def test_manifest_swap_at_export_is_denied(review, monkeypatch):
    approval = review_export.approve_export(**review)
    manifest_path = review["root"] / "manifest.json"
    real_export = review_export.export_viewer

    def swap_manifest(*args, **kwargs):
        manifest = json.loads(manifest_path.read_bytes())
        manifest["limitations"].append("Replaced after approval consumption")
        manifest_path.write_bytes(canonical(manifest))
        return real_export(*args, **kwargs)

    monkeypatch.setattr(review_export, "export_viewer", swap_manifest)
    with pytest.raises(ValidationError, match="Manifest changed after export approval"):
        review_export.redeem_export(**review, approval=approval)
    assert not review["output"].exists()


def test_export_approval_binds_remediation(review):
    from labproof.brief import demo_clients, make_brief

    brief_dir = review["output"].parent / "remediation"
    search, gateway = demo_clients(review["root"])
    make_brief(review["root"], brief_dir, search, gateway, mode="demo")
    options = {**review, "brief_dir": brief_dir}
    approval = review_export.approve_export(**options)
    with pytest.raises(ValidationError, match="optional brief"):
        review_export.redeem_export(**review, approval=approval)

    brief = brief_dir / "brief.json"
    original = brief.read_bytes()
    brief.write_bytes(original + b" ")
    with pytest.raises(ValidationError, match="optional brief"):
        review_export.redeem_export(**options, approval=approval)
    assert not review["output"].exists()

    brief.write_bytes(original)
    assert review_export.redeem_export(**options, approval=approval)["runs"] == 1
    assert json.loads(review["output"].read_bytes())["remediation"] == json.loads(original)
