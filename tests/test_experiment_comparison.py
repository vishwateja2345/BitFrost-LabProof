"""Comparison over invented verified runs; no live/runtime claim."""
from copy import deepcopy

import pytest

from labproof import local_engine
from labproof.cli import main
from labproof.contracts import ValidationError
from labproof.experiment_comparison import compare_experiments, verify_comparison
from labproof.local_profiles import default_experiment_plan
from test_local_experiments import mock_session


def test_verified_same_experiment_ignores_fresh_ids(tmp_path, monkeypatch):
    plan = mock_session(tmp_path, monkeypatch)
    before, after = tmp_path / "before", tmp_path / "after"
    local_engine.run_experiments(before, plan)
    local_engine.run_experiments(after, plan)
    result = compare_experiments(before, after)
    assert result["status"] == "comparable"
    assert result["changed_categories"] == []
    assert result["before"]["manifest_sha256"] != result["after"]["manifest_sha256"]
    assert verify_comparison(result, before, after)["valid"]
    result["causal_attribution"] = "proved"
    with pytest.raises(ValidationError):
        verify_comparison(result, before, after)


def test_blocked_experiments_not_comparable(tmp_path, monkeypatch):
    def unavailable(profile):
        raise FileNotFoundError()
    monkeypatch.setattr(local_engine, "provisioned_experiment", unavailable)
    before, after = tmp_path / "blocked-a", tmp_path / "blocked-b"
    for path in (before, after):
        local_engine.run_experiments(path, default_experiment_plan("python"))
    result = compare_experiments(before, after)
    assert result["status"] == "not_comparable" and result["reasons"]
    output = tmp_path / "comparison.json"
    assert main(["compare-experiments", str(before), str(after), "--output", str(output)]) == 0
    assert main(["compare-experiments", str(before), str(after), "--output", str(output)]) == 1
    assert main(["compare-experiments", str(before), str(after), "--output", str(before / "extra.json")]) == 1


def test_comparison_rejects_tampered_inputs(tmp_path, monkeypatch):
    plan = mock_session(tmp_path, monkeypatch)
    before, after = tmp_path / "before", tmp_path / "after"
    local_engine.run_experiments(before, plan)
    local_engine.run_experiments(after, plan)
    (after / "report.json").write_text("{}")
    with pytest.raises(ValidationError):
        compare_experiments(before, after)
