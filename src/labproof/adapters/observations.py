"""Strict, non-executing adapters for reviewed worker output.

Host-created execution/reset metadata is a binding requirement, not an attestation.
The runtime must establish containment, fresh execution and artifact authenticity;
this module never obtains those facts from worker strings or invents image IDs.
"""
from hashlib import sha256
import json
import re

MAX_BYTES = 131072
VARIANTS = ("alpha", "beta", "gamma", "delta")
TOOLS = {"python-ast": "ast", "python-invariants": "unittest", "typescript-node-test": "node:test",
         "c-gcc": "gcc", "rust-cargo-test": "cargo"}
BEHAVIORAL_OPERATIONS = {"python": "python-invariants", "typescript": "typescript-node-test",
                         "c": "c-gcc", "rust": "rust-cargo-test"}
CASE_IDS = tuple(f"case-{i:02}" for i in range(1, 6))
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")


class ObservationError(ValueError):
    """Worker output is not a complete, bound, structurally valid observation."""


def require(ok, message):
    if not ok:
        raise ObservationError(message)


def fields(value, expected, label):
    require(type(value) is dict and set(value) == set(expected.split()), f"Invalid {label} fields")


def decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "Invalid worker output size")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ObservationError("Nonfinite JSON number")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ObservationError("Invalid worker JSON") from exc


def validate_cases(cases):
    require(type(cases) is list and len(cases) == 5, "Exactly five cases are required")
    seen = {}
    for row in cases:
        fields(row, "case_id response", "case")
        case_id = row["case_id"]
        require(type(case_id) is str and case_id in CASE_IDS and case_id not in seen, "Unknown/duplicate case ID")
        response = row["response"]
        fields(response, "status body", "response")
        require(type(response["status"]) is int and 100 <= response["status"] <= 599, "Invalid response status")
        body = response["body"]
        require(type(body) is dict and len(body) <= 4, "Invalid response body")
        require(all(type(k) is str and type(v) is str and len(k) <= 80 and len(v) <= 128 for k, v in body.items()), "Invalid response value")
        seen[case_id] = row
    require(set(seen) == set(CASE_IDS), "Missing case")
    return [seen[case_id] for case_id in CASE_IDS]


def parse_tap(text):
    """Accept the fixed Node native runner's five tests, not arbitrary TAP suites."""
    require(type(text) is str and len(text.encode("utf-8")) <= 32768, "Invalid TAP size")
    lines = text.splitlines()
    require(1 <= len(lines) <= 200 and lines[0] == "TAP version 13", "Invalid TAP header")
    cases, subtests, completed, totals = [], [], [], {}
    plan = False
    yaml_open = False
    duration_seen = False
    pending = None
    for line in lines[1:]:
        if line == "  ---":
            require(not yaml_open and pending is not None and not plan, "Unexpected TAP detail block")
            yaml_open = True
        elif line == "  ...":
            require(yaml_open, "Unexpected TAP detail terminator")
            yaml_open = False
        elif yaml_open:
            require(bool(re.fullmatch(r"  (?:duration_ms: [0-9]+(?:\.[0-9]+)?|type: 'test')", line)), "Unexpected TAP detail")
        elif line.startswith("# Subtest: "):
            require(not plan and pending is None and len(subtests) == len(cases), "Unexpected TAP subtest")
            case_id = line[len("# Subtest: "):]
            require(case_id in CASE_IDS and case_id not in subtests, "Unknown/duplicate TAP subtest")
            subtests.append(case_id)
        elif line.startswith("ok "):
            match = re.fullmatch(r"ok ([1-5]) - (case-0[1-5])", line)
            require(match is not None and not plan and pending is None and len(subtests) == len(completed) + 1, "Invalid TAP test result")
            require(int(match[1]) == len(completed) + 1 and match[2] == subtests[-1], "TAP test sequence mismatch")
            completed.append(match[2])
            pending = match[2]
        elif line.startswith("# {"):
            require(pending is not None and not plan, "Unbound TAP diagnostic")
            row = decode(line[2:].encode("utf-8"))
            require(type(row) is dict and row.get("case_id") == pending, "TAP diagnostic/test mismatch")
            cases.append(row)
            pending = None
        elif line == "1..5":
            require(not plan and pending is None and len(cases) == 5, "Invalid TAP completion plan")
            plan = True
        elif re.fullmatch(r"# (tests|suites|pass|fail|cancelled|skipped|todo) [0-9]+", line):
            require(plan, "TAP totals before completion")
            _, key, count = line.split()
            require(key not in totals, "Duplicate TAP total")
            totals[key] = int(count)
        elif re.fullmatch(r"# duration_ms [0-9]+(?:\.[0-9]+)?", line):
            require(plan and not duration_seen, "Invalid TAP duration")
            duration_seen = True
        else:
            raise ObservationError("Unexpected/incomplete/failed TAP output")
    require(not yaml_open and pending is None and plan and duration_seen, "Incomplete TAP stream")
    require(totals == {"tests": 5, "suites": 0, "pass": 5, "fail": 0, "cancelled": 0, "skipped": 0, "todo": 0}, "Failed or incomplete TAP totals")
    return validate_cases(cases)


def parse_observation(raw: bytes, operation_id, variant) -> dict:
    """Bind complete raw worker output to controller-selected operation/variant."""
    require(type(operation_id) is str and operation_id in TOOLS, "Unknown operation")
    require(type(variant) is str and variant in VARIANTS, "Unknown variant")
    result = decode(raw)
    common = "schema_version operation_id variant tool tool_version status exit_code timed_out truncated"
    fields(result, common + (" stdout stderr" if operation_id == "typescript-node-test" else " observations"), "worker observation")
    require(result["schema_version"] == "worker-observation-1", "Unsupported worker schema")
    require(result["operation_id"] == operation_id and result["variant"] == variant, "Worker request binding mismatch")
    require(result["tool"] == TOOLS[operation_id], "Worker tool mismatch")
    require(type(result["tool_version"]) is str and bool(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[a-zA-Z0-9.+-]*)", result["tool_version"])) and len(result["tool_version"]) <= 80, "Invalid tool version")
    require(result["status"] == "completed" and type(result["exit_code"]) is int and result["exit_code"] == 0, "Worker did not complete successfully")
    require(type(result["timed_out"]) is bool and result["timed_out"] is False and type(result["truncated"]) is bool and result["truncated"] is False, "Timed out/truncated worker result")
    cases, nodes = [], []
    if operation_id == "typescript-node-test":
        require(result["stderr"] == "", "Unexpected Node stderr; review runtime compatibility")
        cases = parse_tap(result["stdout"])
    elif operation_id in BEHAVIORAL_OPERATIONS.values():
        cases = validate_cases(result["observations"])
    else:
        nodes = result["observations"]
        require(type(nodes) is list and 1 <= len(nodes) <= 512, "Invalid AST observations")
        for node in nodes:
            fields(node, "node line", "AST node")
            require(type(node["node"]) is str and node["node"] in ("FunctionDef", "If", "Return", "Import", "ImportFrom"), "Unknown AST node")
            require(type(node["line"]) is int and 1 <= node["line"] <= 16384, "Invalid AST source line")
    return {"schema_version": "parsed-worker-observation-1", "operation_id": operation_id, "variant": variant,
            "tool": result["tool"], "tool_version": result["tool_version"], "raw_sha256": sha256(raw).hexdigest(),
            "raw_text": raw.decode("utf-8"), "cases": cases, "ast_nodes": nodes}


# Host-only invariant derived from reviewed oracle.host-only.json grading notes.
# No fixture module import, no worker-side expected role, no security label from a model.
BOB = {"id": "record-bob", "owner": "bob", "value": "SYNTHETIC-BOB"}
ALICE = {"id": "record-alice", "owner": "alice", "value": "SYNTHETIC-ALICE"}


def classify_cases(cases):
    rows = {row["case_id"]: row["response"] for row in cases}
    controls = {"case-02": {"status": 200, "body": BOB}, "case-03": {"status": 200, "body": ALICE},
                "case-04": {"status": 401, "body": {"error": "unauthorized"}},
                "case-05": {"status": 404, "body": {"error": "not_found"}}}
    if any(rows.get(key) != expected for key, expected in controls.items()):
        return "unknown"
    if rows.get("case-01") == {"status": 200, "body": BOB}:
        return "exposed"
    if rows.get("case-01") == {"status": 403, "body": {"error": "forbidden"}}:
        return "safe"
    return "unknown"


def adjudicate_observations(records: list[dict], pack_id=None) -> list[dict]:
    """Grade trusted host wrappers. Freshness IDs must come from accepted runtime.

    Invalid wrappers raise; missing valid runs remain not_tested/inconclusive.
    Distinct IDs prevent accidental reuse, not malicious fabrication by a host.
    """
    require(pack_id is None or type(pack_id) is str and pack_id in BEHAVIORAL_OPERATIONS, "Unknown pack filter")
    require(type(records) is list and len(records) <= 40, "Invalid observation records")
    index, ids, executions, resets = {}, set(), set(), set()
    for record in records:
        fields(record, "id phase execution_id reset_id observation", "host record")
        for key, seen in (("id", ids), ("execution_id", executions), ("reset_id", resets)):
            value = record[key]
            require(type(value) is str and bool(TOKEN.fullmatch(value)) and value not in seen, f"Invalid/reused {key}")
            seen.add(value)
        require(type(record["phase"]) is str and record["phase"] in ("observation", "verification"), "Unknown phase")
        parsed = record["observation"]
        require(type(parsed) is dict and type(parsed.get("raw_text")) is str and len(parsed["raw_text"]) <= MAX_BYTES, "Invalid parsed observation")
        try:
            checked = parse_observation(parsed["raw_text"].encode("utf-8"), parsed.get("operation_id"), parsed.get("variant"))
        except UnicodeError as exc:
            raise ObservationError("Invalid raw observation text") from exc
        require(parsed == checked, "Parsed observation/raw binding mismatch")
        slot = (checked["operation_id"], checked["variant"], record["phase"])
        require(slot not in index, "Duplicate operation/variant/phase")
        index[slot] = record
    findings = []
    for pack, operation in BEHAVIORAL_OPERATIONS.items():
        if pack_id is not None and pack != pack_id:
            continue
        for variant in VARIANTS:
            own = [index[(operation, variant, p)] for p in ("observation", "verification") if (operation, variant, p) in index]
            static = [r for (op, v, _), r in index.items() if pack == "python" and op == "python-ast" and v == variant]
            relevant = own + static
            status, reason = "inconclusive", "Missing fresh verification, inconsistent responses, or nonfunctional controls."
            if not own:
                status, reason = "not_tested", "No behavioral observations; static AST output cannot confirm authorization behavior."
            elif len(own) == 2 and len({r["observation"]["tool_version"] for r in own}) == 1:
                outcomes = [classify_cases(r["observation"]["cases"]) for r in own]
                if outcomes == ["safe", "safe"]:
                    status, reason = "rejected", "Both fresh passes enforce the synthetic invariant with functioning legitimate and negative controls."
                elif outcomes == ["exposed", "exposed"]:
                    controls = [index[(operation, v, p)] for v in ("beta", "gamma") for p in ("observation", "verification") if (operation, v, p) in index]
                    relevant += [r for r in controls if r not in relevant]
                    if (len(controls) == 4 and all(classify_cases(r["observation"]["cases"]) == "safe" for r in controls)
                            and len({r["observation"]["tool_version"] for r in own + controls}) == 1):
                        status, reason = "confirmed", "Exact synthetic cross-user disclosure in two fresh passes, with corrected and normal baselines enforcing the invariant and legitimate controls working."
                    else:
                        reason = "Cross-user content observed, but corrected/normal baseline verification is absent, inconsistent, or nonfunctional."
            findings.append({"id": f"finding_{pack}_authorization_{variant}", "title": "Synthetic cross-user object authorization",
                             "pack_id": pack, "operation_id": operation, "variant": variant, "status": status,
                             "expected": "Alice cannot read Bob's synthetic record; legitimate, unknown-actor, and missing-record controls remain functional.",
                             "observed": reason, "evidence_ids": [r["id"] for r in relevant],
                             "limitations": ["Synthetic implementation fixture, not an approved model-effectiveness benchmark.",
                                             "Fresh execution/reset IDs are host bindings; this pure validator does not attest isolation or authenticity."]})
    return findings
