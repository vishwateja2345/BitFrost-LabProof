"""Read-only offline consistency verification, never replay execution."""
from hashlib import sha256
from pathlib import Path

from .contracts import (ID_RE, SHA_RE, MAX_FILES, ValidationError, canonical, check_no_links,
                        parse_json, read_safe, require, strings, timestamp, validate_manifest)
from .policy import Action, Check, Limits, PHASES, VARIANTS
from .report import adjudicate, replay_narrative
from .transport import Response


def _unique(items, label):
    require(isinstance(items, list) and len(items) <= 100, f"Invalid {label} array")
    result = {}
    for item in items:
        require(isinstance(item, dict) and isinstance(item.get("id"), str) and ID_RE.fullmatch(item["id"]), f"Invalid {label} ID")
        require(item["id"] not in result, f"Duplicate {label} ID")
        result[item["id"]] = item
    return result


def _jsonl(raw):
    if not raw:
        return []
    require(raw.endswith(b"\n"), "JSONL missing final newline")
    rows = raw.splitlines()
    require(len(rows) <= 500, "Too many JSONL records")
    require(all(rows), "Blank JSONL record")
    return [parse_json(row) for row in rows]


def _verify(root):
    root = Path(root).absolute()
    check_no_links(root)
    require(root.is_dir(), "Run directory missing")
    manifest = parse_json(read_safe(root, "manifest.json"))
    validate_manifest(manifest)
    require(manifest["mode"] == "replay", "This version verifies replay only; live/local is unsupported")
    payloads = {}
    for artifact in manifest["artifacts"]:
        raw = read_safe(root, artifact["path"])
        require(len(raw) == artifact["bytes"], f"Size mismatch: {artifact['path']}")
        require(sha256(raw).hexdigest() == artifact["sha256"], f"Digest mismatch: {artifact['path']}")
        payloads[artifact["path"]] = raw
    actual = set()
    for number, path in enumerate(root.rglob("*")):
        require(number <= MAX_FILES * 2, "Too many directory entries")
        check_no_links(path)
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
        else:
            require(path.is_dir(), "Special filesystem entry forbidden")
    require(actual == set(payloads) | {"manifest.json"}, "Unregistered or missing files")
    report = parse_json(payloads["report.json"])
    require(isinstance(report, dict), "Invalid report")
    for key in ("project_id", "run_id", "mode", "status"):
        require(report.get(key) == manifest[key], f"Report/manifest {key} mismatch")
    for field in ("title", "summary"):
        require(isinstance(report.get(field), str) and report[field], f"Missing report {field}")
    strings(report.get("limitations"), "report limitations")
    require(report["limitations"] == manifest["limitations"], "Limitation mismatch")
    require(report.get("public_remediation_claims") == [], "Replay cannot carry public remediation claims; curate separately")
    require(report.get("provenance") == {"decisions": "scripted_catalogue", "observations": "synthetic_fixture", "verification": "same_snapshot_replay", "model": "not_used"}, "Invalid replay provenance")
    config = parse_json(payloads["config.json"])
    require(isinstance(config, dict) and set(config) == {"package_version", "limits", "mode", "fixture_sha256", "code_sha256"}, "Invalid config")
    require(isinstance(config["package_version"], str) and config["mode"] == "replay", "Invalid package config")
    require(isinstance(config["code_sha256"], str) and SHA_RE.fullmatch(config["code_sha256"]), "Invalid source code hash")
    require(isinstance(config["limits"], dict), "Invalid limit config")
    limits = Limits(**config["limits"])
    fixture_sha = config["fixture_sha256"]
    if "fixture.json" in payloads:
        require(fixture_sha == sha256(payloads["fixture.json"]).hexdigest(), "Fixture hash mismatch")
        fixture = parse_json(payloads["fixture.json"])
        require(isinstance(fixture, dict) and fixture.get("schema_version") == "1.0" and isinstance(fixture.get("provenance"), str) and isinstance(fixture.get("responses"), dict), "Invalid fixture")
    else:
        require(fixture_sha is None and manifest["status"] != "completed", "Missing fixture")
        fixture = None
    evidence = _unique(report.get("evidence"), "evidence")
    slots = set()
    byte_count = 0
    for item in evidence.values():
        required = {"id", "title", "content", "artifact_path", "sha256", "check_id", "actor_id", "variant", "control", "phase", "response", "source", "fixture_sha256"}
        require(set(item) == required, "Invalid evidence shape")
        action = Action.parse({key: item[key] for key in ("check_id", "actor_id", "control")})
        require(item["variant"] in VARIANTS and item["phase"] in PHASES, "Invalid evidence variant/phase")
        require(item["source"] == "synthetic_fixture" and fixture is not None and item["fixture_sha256"] == fixture_sha, "Dangling evidence provenance")
        slot = (item["check_id"], item["variant"], item["control"], item["phase"])
        require(slot not in slots, "Duplicate evidence slot")
        slots.add(slot)
        require(isinstance(item["title"], str) and item["title"], "Invalid evidence title")
        response = Response.parse(item["response"])
        require(item["content"] == response.body, "Evidence content/response mismatch")
        require(item["response"] == fixture["responses"][item["variant"]][action.check_id.value][item["control"]], "Response differs from registered replay source")
        byte_count += len(canonical(item["response"]))
        require(len(canonical(item["response"])) <= limits.max_response_bytes, "Response exceeds configured budget")
        relative = item["artifact_path"]
        require(isinstance(relative, str) and relative in payloads, "Dangling evidence artifact")
        payload = {key: item[key] for key in ("check_id", "actor_id", "variant", "control", "phase", "response", "source", "fixture_sha256")}
        require(parse_json(payloads[relative]) == payload, "Evidence payload mismatch")
        digest = sha256(payloads[relative]).hexdigest()
        require(item["sha256"] == digest and item["id"] == "ev_" + digest[:24] and relative == f"evidence/{item['id']}.json", "Evidence identity/digest mismatch")
    expected_payloads = {"report.json", "config.json", "events.jsonl", "errors.jsonl"} | {item["artifact_path"] for item in evidence.values()}
    if fixture is not None:
        expected_payloads.add("fixture.json")
    require(set(payloads) == expected_payloads, "Unreferenced artifacts")
    findings = _unique(report.get("findings"), "finding")
    for finding in findings.values():
        for field in ("title", "expected", "observed"):
            require(isinstance(finding.get(field), str) and finding[field], f"Invalid finding {field}")
        require(finding.get("status") in ("confirmed", "rejected", "inconclusive", "not_tested"), "Invalid finding status")
        refs = finding.get("evidence_ids")
        strings(refs, "evidence_ids")
        require(len(refs) == len(set(refs)) and all(ref in evidence for ref in refs), "Duplicate/dangling evidence reference")
    expected_findings = adjudicate(list(evidence.values()))
    require(report["findings"] == expected_findings, "Findings do not match deterministic evidence adjudication")
    for field, expected in replay_narrative(manifest["status"], expected_findings).items():
        require(report.get(field) == expected, f"Report {field} does not match deterministic replay narrative")
    usage = report.get("usage")
    require(isinstance(usage, dict) and set(usage) == {"tool_attempts", "response_bytes", "model_calls", "model_usage", "model_usage_status"}, "Invalid usage")
    require(type(usage["tool_attempts"]) is int and len(evidence) <= usage["tool_attempts"] <= limits.max_actions, "Invalid action accounting")
    require(type(usage["response_bytes"]) is int and byte_count <= usage["response_bytes"] <= limits.max_total_bytes, "Invalid byte accounting")
    require(type(usage["model_calls"]) is int and usage["model_calls"] == 0 and usage["model_usage"] is None and usage["model_usage_status"] == "not_applicable_replay", "Invalid model accounting")
    errors = _unique(_jsonl(payloads["errors.jsonl"]), "error")
    for error in errors.values():
        require(set(error) == {"id", "type", "message"} and all(isinstance(v, str) and v for v in error.values()), "Invalid error record")
    events = _jsonl(payloads["events.jsonl"])
    require(2 <= len(events), "Missing run event boundaries")
    require(events[0].get("type") == "run_started", "Missing run_started")
    seen_evidence, seen_errors, selected, last_time = [], [], [], timestamp(manifest["created_at"])
    reset_phases = []
    for sequence, event in enumerate(events, 1):
        require(isinstance(event, dict) and set(event) == {"sequence", "type", "run_id", "timestamp", "data"}, "Invalid event")
        require(type(event["sequence"]) is int and event["sequence"] == sequence, "Event sequence gap")
        require(event["run_id"] == manifest["run_id"], "Event run ID mismatch")
        current = timestamp(event["timestamp"])
        require(current >= last_time, "Event timestamp moved backwards")
        last_time = current
        kind, data = event["type"], event["data"]
        require(isinstance(kind, str) and isinstance(data, dict), "Invalid event fields")
        if kind == "run_started":
            require(sequence == 1 and data == {"mode": "replay"}, "Invalid run start")
        elif kind == "snapshot_reset":
            require(set(data) == {"phase", "kind"} and data["kind"] == "frozen_fixture_reload", "Invalid reset")
            require(len(reset_phases) < 2 and data["phase"] == PHASES[len(reset_phases)], "Invalid reset phase")
            reset_phases.append(data["phase"])
        elif kind == "action_selected":
            require(set(data) == {"check_id", "actor_id", "control", "variant", "phase"}, "Invalid selected action")
            Action.parse({key: data[key] for key in ("check_id", "actor_id", "control")})
            require(data["variant"] in VARIANTS and reset_phases and data["phase"] == reset_phases[-1], "Invalid action phase")
            selected.append(data)
        elif kind == "evidence_collected":
            require(set(data) == {"evidence_id"} and isinstance(data["evidence_id"], str) and data["evidence_id"] in evidence, "Dangling event evidence")
            item = evidence[data["evidence_id"]]
            require(sequence > 1 and events[sequence - 2]["type"] == "action_selected", "Evidence lacks preceding action")
            require(all(item[k] == v for k, v in events[sequence - 2]["data"].items()), "Action/evidence mismatch")
            seen_evidence.append(data["evidence_id"])
        elif kind == "run_error":
            require(set(data) == {"error_id"} and isinstance(data["error_id"], str) and data["error_id"] in errors, "Dangling event error")
            seen_errors.append(data["error_id"])
        elif kind in ("run_completed", "run_stopped"):
            require(sequence == len(events) and data == {"status": manifest["status"], "evidence_count": len(evidence)}, "Invalid final event")
        else:
            raise ValidationError("Unknown event type")
    require(len(seen_evidence) == len(set(seen_evidence)) and set(seen_evidence) == set(evidence), "Missing/duplicate evidence events")
    require(len(seen_errors) == len(set(seen_errors)) and set(seen_errors) == set(errors), "Missing/duplicate error events")
    require(len(evidence) <= usage["tool_attempts"] <= len(selected), "Event/action accounting mismatch")
    if manifest["status"] == "completed":
        require(events[-1]["type"] == "run_completed", "Missing completion marker")
        require(not errors and len(evidence) == 36 and usage["tool_attempts"] == 36 and len(selected) == 36 and usage["response_bytes"] == byte_count, "Completed run has missing actions/errors")
    else:
        require(events[-1]["type"] == "run_stopped" and errors, "Incomplete run needs stop/error markers")
    return {"valid": True, "project_id": "labproof", "run_id": manifest["run_id"], "status": manifest["status"], "complete": manifest["status"] == "completed", "artifact_count": len(payloads), "limitation": "Internal consistency only; unsigned hashes are not authenticity or proof of a live assessment."}


def verify_artifacts(root):
    try:
        manifest = parse_json(read_safe(Path(root).absolute(), "manifest.json"))
        validate_manifest(manifest)
        if manifest["mode"] == "local":
            from .verify_local import verify_local
            return verify_local(root)
        return _verify(root)
    except ValidationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise ValidationError(f"Invalid artifact bundle ({type(exc).__name__})") from exc
