"""Pure hand-authored parser/adjudicator tests; no worker or fixture execution."""
from copy import deepcopy
import json

import pytest

from labproof.adapters import ObservationError, parse_observation, adjudicate_observations

OPS = {"python-invariants": "unittest", "typescript-node-test": "node:test", "c-gcc": "gcc", "rust-cargo-test": "cargo"}


def cases(variant):
    bob = {"id": "record-bob", "owner": "bob", "value": "SYNTHETIC-BOB"}
    alice = {"id": "record-alice", "owner": "alice", "value": "SYNTHETIC-ALICE"}
    responses = [{"status": 200, "body": bob} if variant == "alpha" else {"status": 403, "body": {"error": "forbidden"}},
                 {"status": 200, "body": bob}, {"status": 200, "body": alice},
                 {"status": 401, "body": {"error": "unauthorized"}}, {"status": 404, "body": {"error": "not_found"}}]
    if variant == "delta":
        responses = [r if i == 3 else {"status": 503, "body": {"error": "unavailable"}} for i, r in enumerate(responses)]
    return [{"case_id": f"case-{i:02}", "response": r} for i, r in enumerate(responses, 1)]


def tap(rows):
    lines = ["TAP version 13"]
    for i, row in enumerate(rows, 1):
        lines.extend([f"# Subtest: {row['case_id']}", f"ok {i} - {row['case_id']}",
                      "  ---", "  duration_ms: 0.123", "  type: 'test'", "  ...", "# " + json.dumps(row)])
    lines.extend(["1..5", "# tests 5", "# suites 0", "# pass 5", "# fail 0", "# cancelled 0", "# skipped 0", "# todo 0", "# duration_ms 12.345"])
    return "\n".join(lines) + "\n"


def output(operation="python-invariants", variant="alpha"):
    obj = {"schema_version": "worker-observation-1", "operation_id": operation, "variant": variant,
           "tool": OPS.get(operation, "ast"), "tool_version": "24.1.0" if operation == "typescript-node-test" else "3.12.10",
           "status": "completed", "exit_code": 0, "timed_out": False, "truncated": False}
    if operation == "typescript-node-test":
        obj.update(stdout=tap(cases(variant)), stderr="")
    else:
        obj["observations"] = [{"node": "FunctionDef", "line": 8}] if operation == "python-ast" else cases(variant)
    return obj


def raw(obj):
    return json.dumps(obj, separators=(",", ":")).encode()


def record(operation, variant, phase):
    identity = f"{operation}-{variant}-{phase}"
    return {"id": "ev-" + identity, "phase": phase, "execution_id": "exec-" + identity,
            "reset_id": "reset-" + identity, "observation": parse_observation(raw(output(operation, variant)), operation, variant)}


def records(operation="python-invariants"):
    return [record(operation, variant, phase) for variant in ("alpha", "beta", "gamma", "delta") for phase in ("observation", "verification")]


@pytest.mark.parametrize("operation", [*OPS, "python-ast"])
@pytest.mark.parametrize("variant", ["alpha", "beta", "gamma", "delta"])
def test_supported_observation_shapes(operation, variant):
    data = raw(output(operation, variant))
    parsed = parse_observation(data, operation, variant)
    assert parsed["raw_text"].encode() == data
    assert parsed["variant"] == variant
    assert len(parsed["cases"]) == (0 if operation == "python-ast" else 5)


@pytest.mark.parametrize("field,value", [("status", "tool-error"), ("exit_code", False), ("exit_code", 1), ("timed_out", True),
    ("timed_out", 0), ("truncated", True), ("truncated", 0), ("tool", "pytest"), ("schema_version", "2"),
    ("variant", "beta"), ("operation_id", "python-ast"), ("tool_version", "garbage")])
def test_reject_worker_failures_and_binding(field, value):
    obj = output(); obj[field] = value
    with pytest.raises(ObservationError):
        parse_observation(raw(obj), "python-invariants", "alpha")


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "bool", "body", "unknown", "field"])
def test_bad_cases(mutation):
    obj = output(); rows = obj["observations"]
    if mutation == "missing": rows.pop()
    elif mutation == "extra": rows.append(deepcopy(rows[0]))
    elif mutation == "duplicate": rows[-1] = deepcopy(rows[0])
    elif mutation == "bool": rows[0]["response"]["status"] = True
    elif mutation == "body": rows[0]["response"]["body"] = {"value": "a" * 129}
    elif mutation == "unknown": rows[0]["case_id"] = "case-06"
    else: rows[0]["expected"] = "confirmed"
    with pytest.raises(ObservationError): parse_observation(raw(obj), "python-invariants", "alpha")


@pytest.mark.parametrize("data", [b"", b" " * 131073, b"\xff", b"{}{}", b'{"x":NaN}', b'{"x":1,"x":2}', b'[' * 2000],
                         ids=["empty", "oversized", "invalid-utf8", "trailing-json", "nan", "duplicate-key", "deep-nesting"])
def test_invalid_json(data):
    with pytest.raises(ObservationError): parse_observation(data, "python-invariants", "alpha")


@pytest.mark.parametrize("op,variant", [("python-pytest", "alpha"), ("c-clang", "alpha"), ("shell", "alpha"), ("python-invariants", "defective"), ([], "alpha"), ("python-invariants", [])])
def test_unknown_operation_variant(op, variant):
    with pytest.raises(ObservationError): parse_observation(raw(output()), op, variant)


@pytest.mark.parametrize("mutation", ["missing_field", "extra_field", "duplicate_key", "bool_ast", "empty_ast"])
def test_strict_shape(mutation):
    obj = output("python-ast")
    if mutation == "missing_field": obj.pop("tool")
    elif mutation == "extra_field": obj["diagnostic"] = "surprise"
    elif mutation == "bool_ast": obj["observations"][0]["line"] = True
    elif mutation == "empty_ast": obj["observations"] = []
    data = raw(obj)
    if mutation == "duplicate_key": data = data.replace(b'"line":8', b'"line":8,"line":9')
    with pytest.raises(ObservationError): parse_observation(data, "python-ast", "alpha")


@pytest.mark.parametrize("mutation", ["fail", "skip", "bail", "missing_plan", "missing_case", "extra_case", "wrong_case", "bad_total", "stderr", "garbage"])
def test_node_tap_failures(mutation):
    obj = output("typescript-node-test")
    replacements = {"fail": ("ok 1", "not ok 1"), "skip": ("ok 1 - case-01", "ok 1 - case-01 # SKIP"),
                    "bail": ("1..5", "Bail out!"), "missing_plan": ("1..5\n", ""),
                    "missing_case": ('# ' + json.dumps(cases("alpha")[0]) + '\n', ''),
                    "wrong_case": ('"case_id": "case-01"', '"case_id": "case-02"'),
                    "bad_total": ("# pass 5", "# pass 4")}
    if mutation in replacements: obj["stdout"] = obj["stdout"].replace(*replacements[mutation])
    elif mutation == "extra_case": obj["stdout"] += '# ' + json.dumps(cases("alpha")[0]) + '\n'
    elif mutation == "stderr": obj["stderr"] = "unexpected warning"
    else: obj["stdout"] += "unexpected\n"
    with pytest.raises(ObservationError): parse_observation(raw(obj), "typescript-node-test", "alpha")


@pytest.mark.parametrize("pack,operation", [("python", "python-invariants"), ("typescript", "typescript-node-test"), ("c", "c-gcc"), ("rust", "rust-cargo-test")])
def test_controls_and_fresh_passes(pack, operation):
    findings = adjudicate_observations(records(operation), pack_id=pack)
    assert [f["status"] for f in findings] == ["confirmed", "rejected", "rejected", "inconclusive"]
    assert len(findings[0]["evidence_ids"]) == 6


@pytest.mark.parametrize("remove", ["verification", "beta", "gamma", "all"])
def test_missing_control_or_verification_never_confirms(remove):
    values = records()
    if remove == "all": values = []
    elif remove == "verification": values = [v for v in values if v["phase"] != remove]
    else: values = [v for v in values if v["observation"]["variant"] != remove]
    assert not any(f["status"] == "confirmed" for f in adjudicate_observations(values))


@pytest.mark.parametrize("key", ["id", "execution_id", "reset_id"])
def test_reused_provenance_rejected(key):
    values = records(); values[1][key] = values[0][key]
    with pytest.raises(ObservationError): adjudicate_observations(values)


def test_duplicate_slot_rejected():
    values = records(); dup = deepcopy(values[0])
    for key in ("id", "execution_id", "reset_id"): dup[key] += "-different"
    values.append(dup)
    with pytest.raises(ObservationError): adjudicate_observations(values)


@pytest.mark.parametrize("mutation", ["digest", "normalized", "raw", "wrapper", "phase"])
def test_record_reparse_binding(mutation):
    values = records(); parsed = values[0]["observation"]
    if mutation == "digest": parsed["raw_sha256"] = "0" * 64
    elif mutation == "normalized": parsed["cases"][0]["response"]["status"] = 403
    elif mutation == "raw": parsed["raw_text"] += " "
    elif mutation == "wrapper": values[0]["authenticated"] = True
    else: values[0]["phase"] = "fresh"
    with pytest.raises(ObservationError): adjudicate_observations(values)


def test_ast_never_confirms_and_filter_excludes_unrelated():
    values = [record("python-ast", "alpha", phase) for phase in ("observation", "verification")]
    findings = adjudicate_observations(values, pack_id="python")
    assert len(findings) == 4 and all(f["status"] == "not_tested" for f in findings)
    assert len(findings[0]["evidence_ids"]) == 2
    assert len(adjudicate_observations([])) == 16
    with pytest.raises(ObservationError): adjudicate_observations([], pack_id="unknown")


@pytest.mark.parametrize("damage", ["body", "legitimate", "version", "safe-alpha"])
def test_content_not_label_or_status_determines_finding(damage):
    values = records()
    for value in values:
        parsed = value["observation"]
        if parsed["variant"] != "alpha": continue
        obj = json.loads(parsed["raw_text"])
        if damage == "body": obj["observations"][0]["response"]["body"] = {"owner": "bob"}
        elif damage == "legitimate": obj["observations"][1]["response"]["body"] = {}
        elif damage == "version": obj["tool_version"] = "3.13.0"
        else: obj["observations"][0]["response"] = {"status": 403, "body": {"error": "forbidden"}}
        value["observation"] = parse_observation(raw(obj), "python-invariants", "alpha")
    result = adjudicate_observations(values, pack_id="python")[0]
    assert result["status"] == ("rejected" if damage == "safe-alpha" else "inconclusive")
