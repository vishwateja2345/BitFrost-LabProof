"""Generated-input contract tests using invented traces, not runtime acceptance."""
from copy import deepcopy

import pytest

from labproof.codec_profiles import (generation_request, launch_plan, make_replay,
                                    parse_request_output, reservation, validate_request,
                                    validate_replay_source)
from labproof.contracts import ValidationError, canonical
from labproof.local_profiles import validate_experiment_plan, default_experiment_plan
from test_hypothesis_codec import trace


def test_counterexample_replay_binds_actual_bytes_and_all_control_variants():
    source = generation_request("alpha", seed=7, cases=4)
    raw = canonical(trace(defective=True))
    for variant in ("alpha", "beta", "gamma", "delta"):
        request = make_replay(source, raw, 5, variant=variant)
        assert validate_replay_source(request, source, raw) == request
        assert request["replay"]["input_hex"] == "01"
        plan = launch_plan(request, "sha256:" + "a" * 64)
        assert plan.argv[-1] == "01"
        assert reservation(request)["target_invocations"] == 128


def test_corrected_concrete_replay_parses_as_observation_only():
    source = generation_request("alpha", seed=7, cases=4)
    request = make_replay(source, canonical(trace(defective=True)), 5, variant="beta")
    observation = parse_request_output(request, canonical(trace(replay="01")))
    assert observation["observation"] == "satisfied"
    assert observation["target_invocations"] == 7


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(seed=True), lambda r: r.update(cases=17),
    lambda r: r.update(variant="../../x"), lambda r: r.update(property="shell"),
    lambda r: r.update(image="sha256:" + "a" * 64),
    lambda r: r.update(schema_version="experiment-plan-2"),
    lambda r: r["replay"].update(input_hex="02"),
    lambda r: r["replay"].update(example_id=True),
    lambda r: r["replay"].update(source_raw_sha256="x"),
])
def test_invalid_requests_fail_closed(mutation):
    source = generation_request("alpha", seed=7, cases=4)
    request = make_replay(source, canonical(trace(defective=True)), 5)
    mutation(request)
    with pytest.raises(ValidationError):
        validate_request(request)


@pytest.mark.parametrize("field", ["source_raw_sha256", "source_request_sha256"])
def test_replay_cannot_rebind_source(field):
    source = generation_request("alpha", seed=7, cases=4)
    raw = canonical(trace(defective=True))
    request = make_replay(source, raw, 5)
    request["replay"][field] = "f" * 64
    with pytest.raises(ValidationError, match="binding"):
        validate_replay_source(request, source, raw)


def test_replay_cannot_change_seed_or_replay_a_replay():
    source = generation_request("alpha", seed=7, cases=4)
    raw = canonical(trace(defective=True))
    request = make_replay(source, raw, 5)
    changed = {**request, "seed": 8}
    with pytest.raises(ValidationError, match="binding"):
        validate_replay_source(changed, source, raw)
    with pytest.raises(ValidationError, match="originate"):
        make_replay(request, canonical(trace(defective=True, replay="01")), 5)
    with pytest.raises(ValidationError, match="generated counterexample"):
        make_replay(source, raw, 1)


def test_satisfied_or_broken_controls_do_not_create_replay():
    source = generation_request("beta", seed=7, cases=4)
    with pytest.raises(ValidationError, match="controlled counterexample"):
        make_replay(source, canonical(trace()), 5)
    broken = trace(defective=True)
    broken["invocations"][0].update(exception="unexpected", output_hex=None)
    with pytest.raises(ValidationError):
        make_replay(generation_request("alpha", seed=7, cases=4), canonical(broken), 5)


def test_codec_requests_cannot_enter_fixed_v2_plan():
    plan = deepcopy(default_experiment_plan("python"))
    plan["steps"][0]["request"] = generation_request("alpha")
    with pytest.raises(ValueError):
        validate_experiment_plan(plan)
