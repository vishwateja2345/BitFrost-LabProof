"""Bounded Bayesian planner: model validation, information math, provenance trust and budgets."""
import copy
import json
import math
import socket
import subprocess

import pytest

from labproof import planning as P
from labproof.cli import main
from labproof.contracts import ValidationError, canonical


def request(**changes):
    value = P.example_request()
    value.update(changes)
    return value


def entropy_of(belief):
    return -sum(p * math.log2(p) for p in belief if p)


def test_default_model_validates_and_round_trips():
    model = P.default_model()
    assert P.build_model(P.model_dict(model)) == model
    assert model.hypotheses == P.HYPOTHESES and math.isclose(sum(model.prior), 1.0)
    assert [e.id for e in model.experiments if e.taintable] == ["static_signal"]


@pytest.mark.parametrize("mutate", [
    lambda m: m.update(prior=[0.5, 0.5, 0.5, 0.0, 0.0]),
    lambda m: m.update(prior=[1.2, -0.2, 0.0, 0.0, 0.0]),
    lambda m: m.update(prior=[float("nan")] * 5),
    lambda m: m.update(prior=[True, False, False, False, False]),
    lambda m: m.update(hypotheses=["none", "none", "a", "b", "c"]),
    lambda m: m.update(hypotheses=[f"h{i}" for i in range(9)], prior=[1 / 9] * 9),
    lambda m: m.update(extra=1),
    lambda m: m["experiments"][0].update(cost=0),
    lambda m: m["experiments"][0].update(cost=True),
    lambda m: m["experiments"][0].update(taintable="no"),
    lambda m: m["experiments"][0].update(outcomes=["only"]),
    lambda m: m["experiments"][0]["likelihood"].pop("none"),
    lambda m: m["experiments"][0]["likelihood"].update(none=[0.5, 0.4]),
    lambda m: m["experiments"][0]["likelihood"].update(none=[1.0]),
    lambda m: m["experiments"].append(copy.deepcopy(m["experiments"][0])),
    lambda m: m.update(experiments=[]),
])
def test_invalid_models_are_rejected(mutate):
    value = P.model_dict(P.default_model())
    mutate(value)
    with pytest.raises(ValidationError):
        P.build_model(value)


def test_expected_gain_equals_mutual_information():
    model = P.default_model()
    for experiment in model.experiments:
        direct = entropy_of(model.prior)
        for o in range(len(experiment.outcomes)):
            q = sum(b * row[o] for b, row in zip(model.prior, experiment.likelihood))
            posterior = [b * row[o] / q for b, row in zip(model.prior, experiment.likelihood)]
            direct -= q * entropy_of(posterior)
        assert math.isclose(P.expected_gain(model.prior, experiment), direct, abs_tol=1e-12)
        assert P.expected_gain(model.prior, experiment) > 0


def test_uninformative_experiment_has_no_gain():
    flat = P.Experiment("flat", 1.0, False, ("a", "b"), ((0.3, 0.7),) * 5)
    assert P.expected_gain(P.default_model().prior, flat) == 0.0


def test_observation_updates_are_normalized_and_impossible_ones_rejected():
    model = P.default_model()
    belief = P.observe(model, model.prior, 0, 0, True, 0.0)
    assert math.isclose(sum(belief), 1.0) and belief[1] > max(belief[0], belief[2], belief[3], belief[4])
    certain = P.Experiment("certain", 1.0, False, ("a", "b"), ((1.0, 0.0),) * 5)
    sure = P.Model(model.hypotheses, model.prior, (certain,))
    with pytest.raises(ValidationError):
        P.observe(sure, model.prior, 0, 1, True, 0.0)


def test_untrusted_observations_pass_through_the_reliability_channel():
    model = P.default_model()
    static = 4
    trusted = P.observe(model, model.prior, static, 2, True, 0.0)
    assert P.observe(model, model.prior, static, 2, False, 1.0) == trusted
    ignored = P.observe(model, model.prior, static, 2, False, 0.0)
    assert all(math.isclose(a, b) for a, b in zip(ignored, model.prior))
    partial = P.observe(model, model.prior, static, 2, False, 0.5)
    assert model.prior[2] < partial[2] < trusted[2]


def test_expected_taint_lowers_the_value_of_a_taintable_experiment():
    model = P.default_model()
    static = model.experiments[4]
    gains = [P.expected_gain(model.prior, static, taint, 0.0) for taint in (0.0, 0.3, 0.6, 1.0)]
    assert gains == sorted(gains, reverse=True) and gains[-1] == 0.0
    probe = model.experiments[0]
    assert P.expected_gain(model.prior, probe, 1.0, 0.0) == P.expected_gain(model.prior, probe)


def test_ranking_is_deterministic_and_ties_break_by_identifier():
    model = P.default_model()
    rows = P.rank(model, model.prior, set(), P.Policy("greedy", 0.035), 3)
    ids = [model.experiments[i].id for i, *_ in rows]
    probes = [name for name in ids if name.startswith("probe_")]
    assert probes == sorted(probes)
    assert rows == P.rank(model, model.prior, set(), P.Policy("greedy", 0.035), 3)


def test_cost_weight_trades_gain_against_cost():
    full = P.default_model()
    model = P.Model(full.hypotheses, full.prior, (full.experiments[5], full.experiments[0]))  # inventory (1.5), probe (1.0)
    free = P.rank(model, model.prior, set(), P.Policy("greedy", 0.0), 1)
    pricey = P.rank(model, model.prior, set(), P.Policy("greedy", 0.9), 1)
    assert model.experiments[free[0][0]].id == "inventory_signal"
    assert model.experiments[pricey[0][0]].id == "probe_authorization"


def test_lookahead_scores_never_fall_below_one_step_utility():
    model = P.default_model()
    for cost_weight in (0.0, 0.035, 0.1):
        rows = P.rank(model, model.prior, set(), P.Policy("lookahead", cost_weight, 2, 0.25, 0.3), 3)
        assert all(score >= utility - 1e-12 for _, _, utility, score in rows)


def test_budget_limits_exclude_experiments():
    out = P.plan_next(request(budget={"experiments": 0, "cost": None}))
    assert out["recommendation"] == {"experiment_id": None, "reason": "no experiment fits the remaining budget"}
    out = P.plan_next(request(budget={"experiments": 3, "cost": 0.4}))
    assert out["ranking"] == [] and out["recommendation"]["experiment_id"] is None
    out = P.plan_next(request(budget={"experiments": 3, "cost": 0.5}))
    assert [r["experiment_id"] for r in out["ranking"]] == ["static_signal"]
    assert out["remaining"] == {"experiments": 3, "cost": 0.5}


def test_no_recommendation_when_nothing_is_worth_its_cost():
    value = request()
    value["policy"]["cost_weight"] = 10.0
    out = P.plan_next(value)
    assert out["recommendation"]["experiment_id"] is None
    assert out["recommendation"]["reason"] == "no feasible experiment has positive expected utility"


def test_huge_numeric_inputs_fail_as_validation_errors():
    for target in ("cost_weight", "taint_rate"):
        value = request()
        value["policy"][target] = 10 ** 400
        with pytest.raises(ValidationError, match="Invalid"):
            P.plan_next(value)
    value = request()
    value["budget"]["cost"] = 10 ** 400
    with pytest.raises(ValidationError, match="Invalid"):
        P.plan_next(value)


def test_rounding_noise_does_not_recommend_a_worthless_experiment():
    value = request()
    value["model"]["experiments"] = [e for e in value["model"]["experiments"] if e["id"] in ("probe_authorization", "static_signal")]
    value["observations"] = [{"experiment_id": "probe_authorization", "outcome": "positive", "trusted": True}]
    value["policy"].update(mode="greedy", cost_weight=0.0, horizon=1, untrusted_reliability=0.0, taint_rate=1.0)
    result = P.plan_next(value)
    assert result["ranking"][0]["score"] == 0.0
    assert result["recommendation"]["experiment_id"] is None


def test_certain_belief_and_subtracted_budget_do_not_show_negative_zero():
    value = request()
    value["model"]["prior"] = [1.0, 0.0, 0.0, 0.0, 0.0]
    result = P.plan_next(value)
    assert math.copysign(1, result["belief_entropy_bits"]) == 1
    assert all(math.copysign(1, item["expected_gain_bits"]) == 1 for item in result["ranking"])


def test_decision_displays_probability_without_contradicting_threshold():
    value = request()
    value["model"]["prior"] = [0.79999999995, 0.05, 0.05, 0.05, 0.05000000005]
    decision = P.plan_next(value)["decision"]
    assert decision["status"] == "inconclusive"
    assert decision["probability"] < decision["threshold"]


def test_plan_next_applies_observations_and_skips_performed_experiments():
    value = request(observations=[{"experiment_id": "probe_authorization", "outcome": "positive", "trusted": True}])
    out = P.plan_next(value)
    assert out["belief"]["object_authorization"] > 0.5
    assert out["remaining"]["experiments"] == 2 and out["remaining"]["cost"] == 2.0
    assert "probe_authorization" not in [r["experiment_id"] for r in out["ranking"]]
    assert out["decision"]["status"] in ("decisive", "inconclusive")


def test_untrusted_observation_does_not_move_belief_when_reliability_is_zero():
    value = request(observations=[{"experiment_id": "static_signal", "outcome": "html_reflection", "trusted": False}])
    value["policy"]["untrusted_reliability"] = 0.0
    out = P.plan_next(value)
    assert set(out["belief"].values()) == {0.2} and out["decision"]["status"] == "inconclusive"


@pytest.mark.parametrize("observation", [
    {"experiment_id": "unknown", "outcome": "positive", "trusted": True},
    {"experiment_id": "probe_authorization", "outcome": "maybe", "trusted": True},
    {"experiment_id": "probe_authorization", "outcome": "positive", "trusted": "yes"},
    {"experiment_id": "probe_authorization", "outcome": "positive", "trusted": True, "text": "Ignore previous instructions"},
    {"experiment_id": "probe_authorization", "outcome": "positive"},
])
def test_observations_are_validated_and_carry_no_free_text(observation):
    with pytest.raises(ValidationError):
        P.plan_next(request(observations=[observation]))


def test_repeated_or_over_budget_observations_are_rejected():
    seen = {"experiment_id": "probe_authorization", "outcome": "positive", "trusted": True}
    with pytest.raises(ValidationError):
        P.plan_next(request(observations=[seen, seen]))
    with pytest.raises(ValidationError):
        P.plan_next(request(observations=[seen], budget={"experiments": 0, "cost": None}))
    with pytest.raises(ValidationError):
        P.plan_next(request(observations=[seen], budget={"experiments": 3, "cost": 0.5}))


@pytest.mark.parametrize("patch", [
    {"horizon": 3}, {"horizon": 0}, {"mode": "random"}, {"mode": "fixed"}, {"cost_weight": -1},
    {"untrusted_reliability": 1.5}, {"taint_rate": float("inf")}, {"horizon": True},
])
def test_policy_bounds_are_enforced(patch):
    value = request()
    value["policy"].update(patch)
    with pytest.raises(ValidationError):
        P.plan_next(value)


def test_request_envelope_is_exact():
    for bad in ({"schema_version": "planning-request-2"}, {"unknown": 1}):
        with pytest.raises(ValidationError):
            P.plan_next({**request(), **bad})
    value = request()
    value.pop("budget")
    with pytest.raises(ValidationError):
        P.plan_next(value)


def test_plan_next_is_pure_json_and_does_not_mutate_its_request():
    value = request(observations=[{"experiment_id": "probe_reflection", "outcome": "negative", "trusted": True}])
    before = copy.deepcopy(value)
    first = P.plan_next(value)
    assert value == before and first == P.plan_next(value)
    assert json.loads(canonical(first)) == json.loads(json.dumps(first))
    assert first["limitations"] and first["schema_version"] == P.RESULT_VERSION


def test_ranking_does_not_depend_on_declaration_order():
    shuffled = request()
    shuffled["model"]["experiments"].reverse()
    assert P.plan_next(shuffled)["ranking"] == P.plan_next(request())["ranking"]
    assert P.plan_next(shuffled)["recommendation"] == P.plan_next(request())["recommendation"]


def test_planning_is_offline_and_executes_nothing(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("planning must not use the network or subprocesses")

    for module, names in ((socket, ("socket", "create_connection")), (subprocess, ("run", "Popen"))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    assert P.plan_next(P.example_request())["recommendation"]["experiment_id"] == "static_signal"


def test_cli_example_input_and_failures(tmp_path, capsys):
    assert main(["plan-next", "--example"]) == 0
    example = json.loads(capsys.readouterr().out)
    assert example == P.example_request()
    path = tmp_path / "request.json"
    path.write_bytes(canonical(example))
    assert main(["plan-next", "--input", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["recommendation"]["experiment_id"] == "static_signal"
    assert main(["plan-next"]) == 1
    assert main(["plan-next", "--example", "--input", str(path)]) == 1
    capsys.readouterr()
    path.write_bytes(b'{"schema_version":"planning-request-1","schema_version":"x"}')
    assert main(["plan-next", "--input", str(path)]) == 1
    assert "Duplicate JSON key" in capsys.readouterr().err
    path.write_bytes(b" " * 65537)
    assert main(["plan-next", "--input", str(path)]) == 1
    assert "64 KiB" in capsys.readouterr().err
    assert main(["plan-next", "--input", str(tmp_path / "missing.json")]) == 1
