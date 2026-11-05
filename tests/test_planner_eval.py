"""Preregistered synthetic planner evaluation: determinism, leakage guards, ledgers and verification."""
from collections import Counter
from hashlib import sha256
import json
import os
import socket
import subprocess

import pytest

from labproof import planner_eval as E
from labproof import planning as P
from labproof.cli import main
from labproof.contracts import ValidationError, canonical

GOLDEN = {
    "preregistration.json": "07cb6b08c7406856b79283c5a41e81845d0bf27871d2362bc7e1452de89ee22c",
    "dev-cases.json": "f80daef3aa6a447a98e6372e2f139403043b20b760beb4b78081dd49bc2e063a",
    "test-cases.json": "25c59e4a7aaa1be9ce1499e62323910906e93179ab5bb70183b9517d0abf4833",
    "lock.json": "2eb80b97dfdfb41ce34227e17f7d04267623d4986f6cc410eb47e052d01fd8c2",
    "dev-candidates.json": "494fc62964aa2e4de28be15633103912f48e6ee0587bc895103091c016a53a16",
    "frozen.json": "6bc4c3b4280df42d3acd1294881a07fa3dd3d1e1db753de146c522c029ee39c9",
    "test-trials.jsonl": "d8d84cc273dfdebca7dc3e1254d0afd0c10d28bd7a655dcff8e74afca87d3b22",
    "analysis.json": "eeb24aa9408e1ca465fd8d34e4b86eef08aa88ea675e933b706002707dd7a637",
}


@pytest.fixture(scope="module")
def artifacts():
    return E.build_artifacts()


@pytest.fixture(scope="module")
def analysis(artifacts):
    return json.loads(artifacts["analysis.json"])


@pytest.fixture(scope="module")
def test_cases(artifacts):
    return {c["id"]: c for c in json.loads(artifacts["test-cases.json"])}


@pytest.fixture(scope="module")
def trials(artifacts):
    return [json.loads(line) for line in artifacts["test-trials.jsonl"].splitlines()]


def digest(raw):
    return sha256(raw).hexdigest()


def test_build_is_deterministic_and_matches_pinned_digests(artifacts):
    assert E.build_artifacts() == artifacts
    assert list(artifacts) == list(E.ARTIFACTS)
    for name, expected in GOLDEN.items():
        assert digest(artifacts[name]) == expected, f"{name} changed: bump PROTOCOL if the rules changed on purpose"


def test_generated_cases_follow_the_declared_simulator():
    for split, per_truth in E.CASES_PER_TRUTH.items():
        cases = E.generate_cases(split)
        assert len(cases) == per_truth * len(P.HYPOTHESES) and len({c["id"] for c in cases}) == len(cases)
        assert Counter(c["truth"] for c in cases) == {h: per_truth for h in P.HYPOTHESES}
        for case in cases:
            assert set(case["observations"]) == {e.id for e in P.default_model().experiments}
            for name, observation in case["observations"].items():
                tainted = not observation["trusted"]
                assert tainted == (case["polluted"] == 1 and name == "static_signal")
                assert (observation["text_sha256"] is not None) == tainted
                if tainted:
                    assert observation["outcome"] != case["truth"]
    assert not {c["id"] for c in E.generate_cases("dev")} & {c["id"] for c in E.generate_cases("test")}
    shifted = E.generate_cases("test")
    assert 0.4 < sum(c["polluted"] for c in shifted) / len(shifted) < 0.7


def test_every_trial_uses_the_same_budget_with_distinct_read_only_experiments(trials):
    model, by_arm = P.default_model(), Counter(t["arm"] for t in trials)
    assert by_arm == {"fixed": 160, "random": 480, "greedy": 160, "blind": 160, "aware": 160}
    assert {t["seed"] for t in trials if t["arm"] == "random"} == set(E.SEEDS)
    for t in trials:
        picked = [s[0] for s in t["steps"]]
        assert len(picked) == E.BUDGET and len(set(picked)) == E.BUDGET
        assert t["cost"] == round(sum(model.experiments[i].cost for i in picked), 6)
        assert t["predicted"] in P.HYPOTHESES and set(t) >= {"correct", "false_positive", "fault_detected"}
    firsts = {arm: {t["steps"][0][0] for t in trials if t["arm"] == arm} for arm in E.ARMS}
    assert firsts["fixed"] == firsts["greedy"] == firsts["blind"] == firsts["aware"] == {4}
    assert len(firsts["random"]) > 3


def test_ledger_chains_are_recomputed_independently(trials, test_cases):
    model = P.default_model()
    for t in trials[::7]:
        case, chain = test_cases[t["case_id"]], "0" * 64
        for index, outcome, trusted in t["steps"]:
            experiment = model.experiments[index]
            observation = case["observations"][experiment.id]
            assert experiment.outcomes[outcome] == observation["outcome"] and bool(trusted) == observation["trusted"]
            event = {"case_id": case["id"], "experiment_id": experiment.id, "outcome": observation["outcome"],
                     "trusted": observation["trusted"], "text_sha256": observation["text_sha256"]}
            chain = sha256((chain + sha256(canonical(event)).hexdigest()).encode()).hexdigest()
        assert t["ledger_terminal_hash"] == chain


def test_untrusted_text_never_changes_a_decision(test_cases):
    model, policy = P.default_model(), E.policy_of({"mode": "greedy", "cost_weight": 0.0, "untrusted_reliability": 0.0, "taint_rate": 0.0})
    tainted = [c for c in test_cases.values() if c["polluted"]][:20]
    assert tainted
    for case in tainted:
        altered = json.loads(json.dumps(case))
        for observation in altered["observations"].values():
            if observation["text_sha256"]:
                observation["text_sha256"] = "0" * 64
        before, after = E.run_case(model, case, policy, 0, {}), E.run_case(model, altered, policy, 0, {})
        assert (before["steps"], before["predicted"]) == (after["steps"], after["predicted"])
        assert before["ledger_terminal_hash"] != after["ledger_terminal_hash"]


def test_policies_are_selected_on_development_cases_only(artifacts, monkeypatch):
    frozen = json.loads(artifacts["frozen.json"])
    model = P.default_model()
    scored, selected = E.select_policies(model, E.generate_cases("dev"))
    assert json.loads(canonical(selected)) == frozen["selected"]
    assert frozen["dev_candidates_sha256"] == digest(artifacts["dev-candidates.json"])
    assert frozen["lock_sha256"] == digest(artifacts["lock.json"])
    lock = json.loads(artifacts["lock.json"])
    assert lock["test_scored_before_freeze"] is False
    assert (lock["dev_sha256"], lock["test_sha256"]) == (digest(artifacts["dev-cases.json"]), digest(artifacts["test-cases.json"]))
    monkeypatch.setitem(E.PROFILES, "test", {**E.PROFILES["test"], "pollution": 0.05, "probe_hit": 0.6})
    changed = E.build_artifacts()
    assert changed["analysis.json"] != artifacts["analysis.json"] and changed["test-cases.json"] != artifacts["test-cases.json"]
    assert json.loads(changed["frozen.json"])["selected"] == frozen["selected"]
    assert changed["dev-candidates.json"] == artifacts["dev-candidates.json"] and changed["dev-cases.json"] == artifacts["dev-cases.json"]


def test_selection_rule_and_blind_subset(artifacts):
    frozen = json.loads(artifacts["frozen.json"])["selected"]
    scored = json.loads(artifacts["dev-candidates.json"])["candidates"]
    assert len(scored) == 2 * 2 * 3 * 3
    top = max(c["utility"] for c in scored)
    assert frozen["aware"]["utility"] == top
    assert frozen["blind"]["blind"] and frozen["blind"]["params"]["untrusted_reliability"] == 1.0
    assert frozen["blind"]["utility"] == max(c["utility"] for c in scored if c["blind"])
    cheapest = min(c["mean_cost"] for c in scored if c["utility"] == top)
    ties = sorted(c["id"] for c in scored if c["utility"] == top and c["mean_cost"] == cheapest)
    assert frozen["aware"]["mean_cost"] == cheapest and frozen["aware"]["id"] == ties[0]
    for c in scored:
        assert c["utility"] == round(c["accuracy"] - 0.5 * c["clean_false_positive_rate"], 6)


def test_tie_break_prefers_lower_cost_then_smaller_identifier():
    pool = [{"id": "b", "utility": 0.5, "mean_cost": 1.0}, {"id": "a", "utility": 0.5, "mean_cost": 2.0},
            {"id": "c", "utility": 0.5, "mean_cost": 1.0}, {"id": "z", "utility": 0.1, "mean_cost": 0.1}]
    assert E.best_candidate(pool)["id"] == "b"
    assert E.best_candidate([pool[2], pool[0]])["id"] == "b"  # equal cost: the smaller identifier wins even when listed later
    assert E.best_candidate([pool[1], pool[2]])["id"] == "c"
    assert E.best_candidate([pool[3], pool[1]])["id"] == "a"


def test_bootstrap_is_deterministic_and_bounded():
    assert E.bootstrap([0.25] * 40, "x") == {"mean_difference": 0.25, "ci95": [0.25, 0.25], "units": 40}
    values = [1.0, 0.0, 0.5, -0.5, 1.0, 0.0, 0.5, 0.5]
    first = E.bootstrap(values, "y")
    assert first == E.bootstrap(values, "y") and first != E.bootstrap(values, "z")
    assert min(values) <= first["ci95"][0] <= first["mean_difference"] <= first["ci95"][1] <= max(values)


def test_analysis_matches_trials_and_preregistered_criteria(analysis, trials, test_cases):
    for arm, summary in analysis["arms"].items():
        rows = [t for t in trials if t["arm"] == arm]
        assert summary["trials"] == len(rows)
        assert summary["accuracy"] == round(sum(t["correct"] for t in rows) / len(rows), 6)
        clean = [t for t in rows if test_cases[t["case_id"]]["truth"] == "none"]
        assert summary["clean_false_positive_rate"] == round(sum(t["false_positive"] for t in clean) / len(clean), 6)
    comparisons = analysis["comparisons"]
    assert comparisons["aware_minus_blind"]["units"] == len(test_cases)
    assert comparisons["aware_minus_blind_polluted"]["units"] + comparisons["aware_minus_blind_unpolluted"]["units"] == len(test_cases)
    expected = {"primary_accuracy_gain": comparisons["aware_minus_blind"]["ci95"][0] > 0,
                "clean_false_positive_not_higher": analysis["arms"]["aware"]["clean_false_positive_rate"] <= analysis["arms"]["blind"]["clean_false_positive_rate"],
                "unpolluted_noninferior": comparisons["aware_minus_blind_unpolluted"]["ci95"][0] >= -E.MARGIN}
    assert analysis["criteria"] == expected
    assert analysis["overall"] == ("supported_on_synthetic_benchmark" if all(expected.values()) else "not_supported")
    assert analysis["limitations"] and analysis["summary"][-1].startswith("preregistered criteria")


def test_the_gain_is_attributed_to_polluted_cases(analysis):
    arms = analysis["arms"]
    assert arms["blind"]["accuracy_polluted"] == 0.0
    assert arms["aware"]["accuracy_polluted"] > 0.4
    assert arms["aware"]["accuracy_unpolluted"] == arms["blind"]["accuracy_unpolluted"]
    assert analysis["comparisons"]["aware_minus_blind_unpolluted"]["mean_difference"] == 0.0


def evaluated(tmp_path):
    out = tmp_path / "evaluation"
    result = E.evaluate_planner(out)
    return out, result


def test_evaluate_writes_a_new_verified_directory(tmp_path, analysis):
    out, result = evaluated(tmp_path)
    assert sorted(os.listdir(out)) == sorted((*E.ARTIFACTS, "manifest.json"))
    assert result["overall"] == analysis["overall"] and result["criteria"] == analysis["criteria"]
    verified = E.verify_planner_evaluation(out)
    assert verified["valid"] and verified["complete"] and verified["reproduced"]
    manifest = json.loads((out / "manifest.json").read_bytes())
    assert [e["path"] for e in manifest["artifacts"]] == list(E.ARTIFACTS) and "manifest.json" not in E.ARTIFACTS
    with pytest.raises(FileExistsError):
        E.evaluate_planner(out)


@pytest.mark.parametrize("name", E.ARTIFACTS)
def test_any_modified_artifact_is_rejected(tmp_path, name):
    out, _ = evaluated(tmp_path)
    path = out / name
    raw = path.read_bytes()
    path.write_bytes(raw[:-2] + (b"0" if raw[-2:-1] != b"0" else b"1") + raw[-1:])
    with pytest.raises(ValidationError, match="digest or size mismatch"):
        E.verify_planner_evaluation(out)


def test_a_coherently_rehashed_forgery_is_still_rejected(tmp_path):
    out, _ = evaluated(tmp_path)
    path = out / "analysis.json"
    forged = path.read_bytes().replace(b'"overall":"supported_on_synthetic_benchmark"', b'"overall":"not_supported"')
    assert forged != path.read_bytes()
    path.write_bytes(forged)
    manifest = json.loads((out / "manifest.json").read_bytes())
    for entry in manifest["artifacts"]:
        if entry["path"] == "analysis.json":
            entry.update(sha256=digest(forged), bytes=len(forged))
    (out / "manifest.json").write_bytes(canonical(manifest))
    with pytest.raises(ValidationError, match="deterministic recomputation"):
        E.verify_planner_evaluation(out)


def test_structure_manifest_and_version_checks(tmp_path):
    out, _ = evaluated(tmp_path)
    (out / "extra.json").write_bytes(b"{}")
    with pytest.raises(ValidationError, match="Unexpected or missing"):
        E.verify_planner_evaluation(out)
    (out / "extra.json").unlink()
    (out / "frozen.json").unlink()
    with pytest.raises(ValidationError, match="Unexpected or missing"):
        E.verify_planner_evaluation(out)
    second = tmp_path / "second"
    second.mkdir()
    other, _ = evaluated(second)
    manifest = json.loads((other / "manifest.json").read_bytes())
    for change in ({"schema_version": "planner-evaluation-2"}, {"kind": "other"}, {"unexpected": 1}, {"limitations": []},
                   {"artifacts": manifest["artifacts"][::-1]}, {"created_at": "yesterday"}):
        (other / "manifest.json").write_bytes(canonical({**manifest, **change}))
        with pytest.raises(ValidationError):
            E.verify_planner_evaluation(other)
    with pytest.raises(OSError):
        E.verify_planner_evaluation(tmp_path / "does-not-exist")


def test_manifest_metadata_and_canonical_bytes_are_verified(tmp_path):
    out, _ = evaluated(tmp_path)
    path = out / "manifest.json"
    original = json.loads(path.read_bytes())
    for modified in ({**original, "package_version": "other"},
                     {**original, "artifacts": [{**original["artifacts"][0], "bytes": float(original["artifacts"][0]["bytes"])}, *original["artifacts"][1:]]}):
        path.write_bytes(canonical(modified))
        with pytest.raises(ValidationError):
            E.verify_planner_evaluation(out)
    path.write_bytes(json.dumps(original, indent=2).encode("utf-8"))
    with pytest.raises(ValidationError, match="canonical"):
        E.verify_planner_evaluation(out)


def test_symlinked_evaluation_is_rejected(tmp_path):
    out, _ = evaluated(tmp_path)
    link = tmp_path / "link"
    try:
        os.symlink(out, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ValidationError, match="Symlink"):
        E.verify_planner_evaluation(link)


def test_evaluation_is_offline_and_executes_nothing(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("evaluation must not use the network or subprocesses")

    for module, names in ((socket, ("socket", "create_connection")), (subprocess, ("run", "Popen"))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    out, _ = evaluated(tmp_path)
    assert E.verify_planner_evaluation(out)["reproduced"]


def test_cli_evaluate_and_verify(tmp_path, capsys, analysis):
    out = tmp_path / "cli-evaluation"
    assert main(["evaluate-planner", "--output", str(out)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["overall"] == analysis["overall"] and result["summary"] == analysis["summary"]
    assert main(["verify-planner-evaluation", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["reproduced"] is True
    assert main(["evaluate-planner", "--output", str(out)]) == 1
    assert "FileExistsError" in capsys.readouterr().err
    (out / "analysis.json").write_bytes(b"{}\n")
    assert main(["verify-planner-evaluation", str(out)]) == 1
    assert "ValidationError" in capsys.readouterr().err
