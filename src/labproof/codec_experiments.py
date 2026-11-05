"""Bounded control/reproduction interpretation for codec experiment records.

Pure host logic, not live acceptance. Each observation is rederived from retained
worker bytes. Runtime callers must separately validate containment and identities.
"""
from .codec_profiles import (digest, generation_request, make_replay, parse_request_output,
                             reservation, validate_request, validate_replay_source)
from .contracts import canonical, require, ID_RE

BUDGET_FIELDS = {"actions", "target_invocations", "wall_seconds", "output_bytes"}
MAXIMA = {"actions": 32, "target_invocations": 4096, "wall_seconds": 3600, "output_bytes": 1_920_000}


def validate_budget(value):
    require(type(value) is dict and set(value) == BUDGET_FIELDS, "Invalid codec budget fields")
    require(all(type(value[k]) is int and 0 <= value[k] <= MAXIMA[k] for k in BUDGET_FIELDS),
            "Invalid codec budget bounds")
    return dict(value)


def reserve_requests(budget, used, requests):
    """Reserve worst-case resources for an entire control/replay batch first."""
    budget, used = validate_budget(budget), validate_budget(used)
    require(type(requests) in (list, tuple) and len(requests) <= MAXIMA["actions"], "Invalid request batch")
    reserved = dict(used)
    for request in requests:
        charge = reservation(request)
        for key in BUDGET_FIELDS:
            reserved[key] += charge[key]
    require(all(reserved[k] <= budget[k] for k in BUDGET_FIELDS), "Mandatory codec batch exceeds budget")
    return reserved


def reproduction_batch(source_request, source_raw, example_id):
    """Exact input against the original and three independent control workers."""
    return [make_replay(source_request, source_raw, example_id, variant=variant)
            for variant in ("alpha", "beta", "gamma", "delta")]


def _record(record, seen):
    require(type(record) is dict and set(record) == {"request", "raw", "execution_id", "reset_id",
            "controller_status", "returncode", "timed_out", "truncated", "cleanup_ok"}, "Invalid codec host record")
    request = validate_request(record["request"])
    identities = set()
    for name in ("execution_id", "reset_id"):
        value = record[name]
        require(type(value) is str and ID_RE.fullmatch(value) and value not in seen,
                "Invalid/reused codec worker identity")
        identities.add(value)
    seen.update(identities)
    require(record["controller_status"] in ("completed", "interrupted"), "Invalid controller status")
    require(record["returncode"] is None or type(record["returncode"]) is int, "Invalid codec return code")
    require(all(type(record[k]) is bool for k in ("timed_out", "truncated", "cleanup_ok")), "Invalid codec flags")
    require(type(record["raw"]) is bytes and len(record["raw"]) <= 60000, "Invalid codec raw bytes")
    safe = (record["controller_status"] == "completed" and record["returncode"] == 0
            and record["cleanup_ok"] and not record["timed_out"] and not record["truncated"])
    if not safe:
        return request, None
    return request, parse_request_output(request, record["raw"])


def interpret_reproduction(source, replays):
    """No claim of exploitability, authenticity or independent effectiveness.

    A nonfunctional ambiguous control is expected to remain inconclusive. It
    cannot serve as a corrected/normal baseline or promote its own finding.
    """
    require(type(replays) is list and len(replays) <= 4, "Invalid codec replay group")
    seen = set()
    source_request, observed = _record(source, seen)
    require(source_request["replay"] is None and source_request["variant"] == "alpha",
            "Expected original defective-fixture generation")
    result = {"schema_version": "codec-interpretation-1", "status": "inconclusive",
              "source_request_sha256": digest(source_request), "replay_outcomes": {},
              "reason": "Missing or incomplete controlled counterexample reproduction.",
              "limitations": ["Synthetic codec behavior only; not exploitability or production security.",
                              "Pure interpretation does not attest runtime acceptance or execution.",
                              "Controls share a host oracle; agreement is not independent confirmation."]}
    selected_input = None
    complete = True
    for record in replays:
        request, replay = _record(record, seen)
        validate_replay_source(request, source_request, source["raw"])
        variant = request["variant"]
        require(variant not in result["replay_outcomes"], "Duplicate control variant")
        key = (request["replay"]["example_id"], request["replay"]["input_sha256"])
        require(selected_input is None or selected_input == key, "Control batch uses different counterexamples")
        selected_input = key
        complete = complete and replay is not None and replay["status"] in ("completed", "counterexample")
        result["replay_outcomes"][variant] = "unavailable" if replay is None else replay["observation"]
    if not complete:
        result["reason"] = "A required replay worker was unsafe, unavailable or did not complete its observation."
        return result
    if observed is None or observed["observation"] != "counterexample":
        return result
    outcomes = result["replay_outcomes"]
    if set(outcomes) != {"alpha", "beta", "gamma", "delta"}:
        return result
    if outcomes == {"alpha": "counterexample", "beta": "satisfied", "gamma": "satisfied", "delta": "inconclusive"}:
        result.update(status="controlled_reproduction", reason="Retained input reproduces the synthetic failure in a fresh worker; corrected/normal controls pass and the ambiguous control abstains.")
    elif outcomes["alpha"] == "satisfied":
        result["reason"] = "The retained counterexample did not reproduce; generation and replay disagree."
    elif outcomes["beta"] != "satisfied" or outcomes["gamma"] != "satisfied":
        result["reason"] = "Corrected or normal control is invalid, failing or incomplete."
    else:
        result["reason"] = "Ambiguous control did not exhibit its required inconclusive behavior."
    return result
