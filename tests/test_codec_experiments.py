"""Invented controller records exercise interpretation, not real containment."""
from copy import deepcopy

import pytest

from labproof.codec_experiments import (interpret_reproduction, reproduction_batch,
                                       reserve_requests, validate_budget)
from labproof.codec_profiles import generation_request
from labproof.contracts import ValidationError, canonical
from test_hypothesis_codec import trace


def record(request, value, index):
    return {"request": request, "raw": canonical(value), "execution_id": f"exec_{index}",
            "reset_id": f"reset_{index}", "controller_status": "completed", "returncode": 0,
            "timed_out": False, "truncated": False, "cleanup_ok": True}


def group():
    request = generation_request("alpha", seed=7, cases=4)
    source = record(request, trace(defective=True), 0)
    requests = reproduction_batch(request, source["raw"], 5)
    records = []
    for index, request in enumerate(requests, 1):
        value = trace(defective=index == 1, replay="01")
        value["variant"] = request["variant"]
        if request["variant"] == "delta":
            # An unexpected target exception must remain inconclusive.
            value["invocations"][-1].update(exception="unexpected", output_hex=None)
            value["examples"][-1]["outcome"] = "counterexample"
            value["status"] = "counterexample"
        records.append(record(request, value, index))
    return source, records


def test_controlled_reproduction_requires_complete_batch():
    source, records = group()
    result = interpret_reproduction(source, records)
    assert result["status"] == "controlled_reproduction"
    assert "confirmed" not in result.values()
    for count in range(4):
        assert interpret_reproduction(source, records[:count])["status"] == "inconclusive"


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("field,value", [("timed_out", True), ("truncated", True),
                                         ("cleanup_ok", False), ("returncode", 1),
                                         ("returncode", None), ("controller_status", "interrupted")])
def test_failed_worker_prevents_promotion(index, field, value):
    source, records = group()
    records[index][field] = value
    result = interpret_reproduction(source, records)
    assert result["status"] == "inconclusive"
    assert result["replay_outcomes"][records[index]["request"]["variant"]] == "unavailable"


def test_observed_nonfunctional_delta_is_distinct_from_worker_failure():
    source, records = group()
    value = trace(replay="01")
    value.update(variant="delta", status="counterexample")
    value["examples"] = [{**value["examples"][0], "outcome": "counterexample"}]
    value["invocations"] = [{**value["invocations"][0], "output_hex": None, "exception": "unexpected"}]
    records[3]["raw"] = canonical(value)
    assert interpret_reproduction(source, records)["status"] == "controlled_reproduction"


@pytest.mark.parametrize("status", ["tool-error", "budget-exhausted"])
def test_ambiguous_tool_error_cannot_stand_in_for_observed_control(status):
    source, records = group()
    value = trace(replay="01")
    value.update(variant="delta", status=status)
    if status == "budget-exhausted":
        # Replay allows only one target call after six controls, so exhausting
        # the invocation cap here is malformed rather than an ambiguous result.
        with pytest.raises(ValidationError, match="exhausted invocation"):
            records[3]["raw"] = canonical(value)
            interpret_reproduction(source, records)
    else:
        records[3]["raw"] = canonical(value)
        assert interpret_reproduction(source, records)["status"] == "inconclusive"


def test_fresh_worker_ids_and_one_counterexample_required():
    source, records = group()
    records[1]["reset_id"] = records[0]["reset_id"]
    with pytest.raises(ValidationError, match="worker identity"):
        interpret_reproduction(source, records)
    source, records = group()
    records[1]["request"]["replay"]["example_id"] = 6
    with pytest.raises(ValidationError, match="different counterexamples"):
        interpret_reproduction(source, records)


def test_nonreproduction_is_not_confirmation():
    source, records = group()
    corrected = trace(replay="01")
    corrected["variant"] = "alpha"
    records[0]["raw"] = canonical(corrected)
    result = interpret_reproduction(source, records)
    assert result["status"] == "inconclusive" and "did not reproduce" in result["reason"]


def test_batch_reserves_invocations_not_just_actions():
    source, records = group()
    requests = [row["request"] for row in records]
    budget = {"actions": 4, "target_invocations": 512, "wall_seconds": 1000, "output_bytes": 240000}
    used = {key: 0 for key in budget}
    reserved = reserve_requests(budget, used, requests)
    assert reserved["actions"] == 4 and reserved["target_invocations"] == 512
    for key in budget:
        lowered = {**budget, key: reserved[key] - 1}
        with pytest.raises(ValidationError, match="exceeds budget"):
            reserve_requests(lowered, used, requests)
    assert used == {key: 0 for key in used}
    with pytest.raises(ValidationError):
        validate_budget({**budget, "actions": True})
