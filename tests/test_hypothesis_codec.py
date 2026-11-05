"""Pure invented trace and AST checks; never import/execute codec or worker."""
import ast
from copy import deepcopy
from pathlib import Path

import pytest

from labproof.adapters.hypothesis_codec import parse_codec
from labproof.contracts import ValidationError, canonical

ROOT = Path(__file__).resolve().parents[1]


def trace(*, defective=False, replay=None):
    examples, calls = [], []

    def add(kind, raw, methods, outcome="satisfied"):
        eid = len(examples) + 1
        examples.append({"id": eid, "kind": kind, "input_hex": raw.hex(), "outcome": outcome})
        for method, input_bytes, output, exception in methods:
            calls.append({"id": len(calls) + 1, "example_id": eid, "method": method,
                          "input_hex": input_bytes.hex(), "output_hex": None if output is None else output.hex(), "exception": exception})

    for kind, raw in (("control-empty", b""), ("control-boundary", b"x" * 255)):
        encoded = bytes([len(raw)]) + raw
        add(kind, raw, [("encode", raw, encoded, None), ("decode", encoded, raw, None)])
    add("control-oversize", b"x" * 256, [("encode", b"x" * 256, None, "ValueError")])
    add("control-empty-frame", b"", [("decode", b"", None, "ValueError")])
    raw = b"\x01" if replay is None else bytes.fromhex(replay)
    # Include duplicate recheck: every target invocation must be counted.
    for _ in range(1 if replay is not None else 2 if defective else 4):
        add("generated" if replay is None else "replay", raw,
            [("decode", raw, b"" if defective else None, None if defective else "ValueError")],
            "counterexample" if defective else "satisfied")
    return {"schema_version": "codec-worker-1", "fixture_id": "python-codec-v1", "variant": "alpha" if defective else "beta",
            "property": "malformed", "seed": 7, "cases": 4, "replay_hex": replay,
            "tool": "hypothesis", "tool_version": "6.142.4",
            "settings": {"database": None, "phases": ["generate"], "deadline": None, "report_multiple_bugs": False, "max_examples": 4},
            "status": "counterexample" if defective else "completed", "invocation_limit": 128,
            "invocations": calls, "examples": examples, "rejections": 0, "shrinks": 0}


def parse(value):
    return parse_codec(canonical(value), variant=value["variant"], property_id="malformed", seed=7, cases=4, replay_hex=value["replay_hex"])


def test_all_calls_including_recheck_counted():
    value = trace(defective=True)
    result = parse(value)
    assert result["controls_ok"] and result["observation"] == "counterexample"
    assert result["target_invocations"] == 8  # 6 control calls + 2 failing generated/recheck calls.
    assert len(result["counterexamples"]) == 2
    assert [c["input_hex"] for c in result["counterexamples"]] == ["01", "01"]
    assert result["rejections"] == result["shrinks"] == 0


def test_exact_corrected_replay_is_observation_not_confirmation():
    result = parse(trace(replay="01"))
    assert result["observation"] == "satisfied" and result["target_invocations"] == 7
    assert "confirmed" not in result.values()


@pytest.mark.parametrize("mutation", [
    lambda v: v.update(tool_version="6.142.5"),
    lambda v: v.update(seed=8),
    lambda v: v.update(cases=True),
    lambda v: v.update(shrinks=1),
    lambda v: v.update(rejections=1),
    lambda v: v.update(invocation_limit=999),
    lambda v: v.update(status="passed"),
    lambda v: v.update(status="budget-exhausted"),
    lambda v: v["settings"].update(database=".hypothesis"),
    lambda v: v["settings"].update(phases=["generate", "shrink"]),
    lambda v: v["invocations"][0].update(id=True),
    lambda v: v["invocations"][0].update(example_id=99),
    lambda v: v["invocations"][0].update(method="shell"),
    lambda v: v["invocations"][0].update(input_hex="not-hex"),
    lambda v: v["invocations"][0].update(output_hex="00" * 258),
    lambda v: v["invocations"][1].update(input_hex="01"),
    lambda v: v["invocations"][0].update(exception="unrecognized"),
    lambda v: v["examples"][0].update(kind="generated"),
    lambda v: v["examples"][0].update(input_hex="01"),
    lambda v: v["examples"][4].update(outcome="counterexample"),
    lambda v: v["examples"].pop(),
    lambda v: v["invocations"].pop(),
])
def test_parser_negatives(mutation):
    value = trace()
    mutation(value)
    with pytest.raises(ValidationError):
        parse(value)


def test_unknown_exception_is_inconclusive_not_defect():
    value = trace(defective=True)
    for call in value["invocations"][-2:]:
        call.update(exception="unexpected", output_hex=None)
    result = parse(value)
    assert result["observation"] == "inconclusive"


def test_completion_requires_all_controls():
    value = trace()
    value["examples"] = value["examples"][:1]
    value["invocations"] = value["invocations"][:2]
    with pytest.raises(ValidationError):
        parse(value)


def test_concrete_replay_mismatch_rejected():
    value = trace(replay="01")
    with pytest.raises(ValidationError):
        parse_codec(canonical(value), variant="beta", property_id="malformed", seed=7, cases=4, replay_hex="02")


def test_truncated_duplicate_and_oversize_output_rejected():
    raw = canonical(trace())
    for malformed in (raw[:-3], b'{"schema_version":1,"schema_version":2}', b"x" * 60001):
        with pytest.raises(ValidationError):
            parse_codec(malformed, variant="beta", property_id="malformed", seed=7, cases=4)


def test_worker_source_is_unregistered_and_never_host_executed():
    source = (ROOT / "sandboxes/python/hypothesis_codec.py").read_text()
    tree = ast.parse(source)
    assert "Phase.generate," in source and "database=None" in source
    assert "Phase.shrink" not in source and "assume(" not in source and ".filter(" not in source
    assert "if len(trace) >= MAX_INVOCATIONS" in source
    assert "trace.append(row)" in source
    assert "spec.loader.exec_module(module)" in source
    for variant in ("alpha", "beta", "gamma", "delta"):
        path = ROOT / f"src/labproof/fixtures/codec/python/{variant}/codec.py"
        ast.parse(path.read_text())  # Syntax only, not compile/exec/import.
    from labproof.local_profiles import EXPERIMENT_PROFILES
    assert all("hypothesis" not in name for name in EXPERIMENT_PROFILES)
