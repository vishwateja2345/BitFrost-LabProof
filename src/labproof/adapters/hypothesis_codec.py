"""Pure parser for UNPROVISIONED codec pilot output; no tool/fixture execution.

This is deliberately not dispatched by the accepted local v1/v2 foundation.
Runtime/profile integration and promotion require separate actual acceptance.
"""
from hashlib import sha256
import re

from ..contracts import canonical, parse_json, require

VERSION = "6.142.4"
MAX_INVOCATIONS = 128
CONTROLS = ("control-empty", "control-boundary", "control-oversize", "control-empty-frame")


def _shape(value, keys):
    require(type(value) is dict and set(value) == set(keys.split()), "Invalid codec fields")


def _hex(value, maximum=257):
    require(type(value) is str and len(value) <= maximum * 2 and len(value) % 2 == 0
            and re.fullmatch(r"[0-9a-f]*", value), "Invalid bounded codec input")
    return bytes.fromhex(value)


def _integer(value, low, high):
    require(type(value) is int and low <= value <= high, "Invalid codec integer")


def _outcome(example, calls):
    """Host derives API invariants from concrete calls, not worker outcome labels."""
    raw = _hex(example["input_hex"])
    kind = example["kind"]
    if not calls:
        return "interrupted"
    first = calls[0]
    require(first["input_hex"] == example["input_hex"], "Example/call input mismatch")
    if kind in ("control-empty-frame", "replay", "generated-malformed"):
        require(first["method"] == "decode" and len(calls) == 1, "Invalid malformed call trace")
        require(not raw or raw[0] != len(raw) - 1, "Expected malformed frame")
        return "satisfied" if first["exception"] == "ValueError" else "counterexample"
    if kind == "control-oversize":
        require(raw == b"x" * 256 and first["method"] == "encode" and len(calls) == 1, "Invalid oversize control")
        return "satisfied" if first["exception"] == "ValueError" else "counterexample"
    require(first["method"] == "encode" and len(raw) <= 255, "Invalid roundtrip trace")
    expected = (bytes([len(raw)]) + raw).hex()
    if first["exception"] is not None or first["output_hex"] != expected:
        require(len(calls) == 1, "Unexpected call after failed encode")
        return "counterexample"
    if len(calls) == 1:
        return "interrupted"
    require(len(calls) == 2 and calls[1]["method"] == "decode" and calls[1]["input_hex"] == expected, "Roundtrip replay mismatch")
    return "satisfied" if calls[1]["exception"] is None and calls[1]["output_hex"] == raw.hex() else "counterexample"


def parse_codec(raw, *, variant, property_id, seed, cases, replay_hex=None):
    require(type(raw) is bytes and 0 < len(raw) <= 60000, "Invalid codec output size")
    require(variant in ("alpha", "beta", "gamma", "delta") and property_id in ("roundtrip", "boundary", "malformed"), "Invalid codec request")
    _integer(seed, 0, 65535)
    _integer(cases, 1, 16)
    if replay_hex is not None:
        frame = _hex(replay_hex)
        require(property_id == "malformed" and (not frame or frame[0] != len(frame) - 1), "Invalid replay request")
    value = parse_json(raw)
    _shape(value, "schema_version fixture_id variant property seed cases replay_hex tool tool_version settings status invocation_limit invocations examples rejections shrinks")
    expected = {"schema_version": "codec-worker-1", "fixture_id": "python-codec-v1", "variant": variant,
                "property": property_id, "seed": seed, "cases": cases, "replay_hex": replay_hex,
                "tool": "hypothesis", "tool_version": VERSION, "invocation_limit": MAX_INVOCATIONS,
                "settings": {"database": None, "phases": ["generate"], "deadline": None,
                             "report_multiple_bugs": False, "max_examples": cases}, "rejections": 0, "shrinks": 0}
    require(all(canonical(value[k]) == canonical(v) for k, v in expected.items()), "Codec request/settings/version mismatch")
    require(value["status"] in ("completed", "counterexample", "budget-exhausted", "tool-error"), "Unknown codec completion")
    calls, examples = value["invocations"], value["examples"]
    require(type(calls) is list and len(calls) <= MAX_INVOCATIONS, "Codec invocation ceiling exceeded")
    require(type(examples) is list and len(examples) <= MAX_INVOCATIONS + 1, "Codec example ceiling exceeded")
    grouped = {}
    last = 0
    for index, call in enumerate(calls, 1):
        _shape(call, "id example_id method input_hex output_hex exception")
        _integer(call["id"], index, index)
        _integer(call["example_id"], 1, len(examples))
        require(call["example_id"] >= last, "Invocation example order mismatch")
        last = call["example_id"]
        require(call["method"] in ("encode", "decode"), "Unreviewed target method")
        _hex(call["input_hex"])
        require(call["exception"] in (None, "ValueError", "unexpected", "invalid-result"), "Unknown target exception")
        if call["exception"] is None:
            _hex(call["output_hex"])
        else:
            require(call["output_hex"] is None, "Exception with target output")
        grouped.setdefault(call["example_id"], []).append(call)
    counterexamples, control_outcomes, generated = [], [], []
    for index, example in enumerate(examples, 1):
        _shape(example, "id kind input_hex outcome")
        _integer(example["id"], index, index)
        payload = _hex(example["input_hex"])
        kind = example["kind"]
        if index <= len(CONTROLS):
            require(kind == CONTROLS[index - 1], "Missing/reordered functional control")
            expected_input = (b"", b"x" * 255, b"x" * 256, b"")[index - 1]
            require(payload == expected_input, "Control input changed")
        else:
            require(kind == ("replay" if replay_hex is not None else "generated"), "Unknown generated/replay example")
            if replay_hex is not None:
                require(index == 5 and example["input_hex"] == replay_hex, "Concrete replay input mismatch")
            elif property_id == "boundary":
                require(payload in (b"", b"x" * 255), "Unbounded boundary input")
            elif property_id == "roundtrip":
                require(len(payload) <= 32, "Unbounded roundtrip input")
            else:
                require(1 <= len(payload) <= 33 and payload[0] == len(payload), "Generated malformed strategy mismatch")
        graded = {**example, "kind": "generated-malformed" if kind == "generated" and property_id == "malformed" else kind}
        outcome = _outcome(graded, grouped.get(index, []))
        require(example["outcome"] == outcome, "Worker outcome disagrees with retained concrete calls")
        if index <= 4:
            control_outcomes.append(outcome)
        else:
            generated.append(outcome)
        if outcome == "interrupted":
            require(index == len(examples) and value["status"] in ("budget-exhausted", "tool-error"), "Interrupted trace cannot complete")
        if outcome == "counterexample":
            counterexamples.append({"example_id": index, "input_hex": example["input_hex"], "kind": kind})
    controls_ok = control_outcomes == ["satisfied"] * 4
    if value["status"] == "completed":
        require(controls_ok and generated and all(v == "satisfied" for v in generated), "Completed codec trace lacks successful controls/examples")
        required_examples = 1 if replay_hex is not None else min(cases, 2) if property_id == "boundary" else cases
        require(len(generated) >= required_examples, "Completed codec trace lacks requested examples")
    elif value["status"] == "counterexample":
        require(bool(counterexamples), "Counterexample absent from concrete trace")
    elif value["status"] == "budget-exhausted":
        require(len(calls) == MAX_INVOCATIONS, "Budget status without exhausted invocation ceiling")
    # Local observation verdict is not a cross-worker confirmed defect.
    observation = "inconclusive"
    if controls_ok and value["status"] == "completed":
        observation = "satisfied"
    elif controls_ok and value["status"] == "counterexample" and any(c["kind"] in ("generated", "replay") for c in counterexamples):
        observation = "counterexample"
    if any(c["exception"] in ("unexpected", "invalid-result") for c in calls):
        observation = "inconclusive"
    return {"schema_version": "parsed-codec-1", "raw_sha256": sha256(raw).hexdigest(),
            "request": {"fixture_id": "python-codec-v1", "variant": variant, "property": property_id,
                        "seed": seed, "cases": cases, "replay_hex": replay_hex},
            "tool_version": VERSION, "status": value["status"], "controls_ok": controls_ok,
            "observation": observation, "invocations": calls, "examples": examples,
            "counterexamples": counterexamples, "target_invocations": len(calls),
            "rejections": 0, "shrinks": 0}
