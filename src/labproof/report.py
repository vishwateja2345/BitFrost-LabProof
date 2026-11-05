"""Deterministic, content-based adjudication, never model self-certification."""
import json
from .policy import CATALOGUE, PHASES, VARIANTS, Check

LIMITATIONS = [
    "Replay only: all HTTP-shaped observations are hand-authored synthetic fixtures, not measurements from a running service.",
    "Scripted catalogue decisions demonstrate evidence plumbing, not model autonomy or a production effectiveness benchmark.",
    "Verification repeats a reset frozen snapshot, not an independent live experiment.",
    "HTML reflection uses harmless emphasis markup only; no scripts, browser execution, or confirmed XSS.",
    "No isolated runtime is verified; actual assessment is blocked. Docker, network isolation and live provider compatibility are untested.",
    "Hashes establish internal artifact consistency, not authenticity, public truth or exploitability.",
    "No public remediation claims are included unless explicitly provided separately; synthetic lab facts are never public remediation claims.",
]
TITLES = {
    Check.AUTHORIZATION: "Synthetic cross-user object disclosure",
    Check.REFLECTION: "Unescaped harmless HTML reflection (not script execution)",
    Check.DISCLOSURE: "Verbose synthetic error disclosure",
}
EXPECTED = {
    Check.AUTHORIZATION: "Alice cannot retrieve Bob's synthetic record; Bob's normal authorized access remains functional.",
    Check.REFLECTION: "Harmless emphasis markup is escaped in HTML text; normal text remains functional.",
    Check.DISCLOSURE: "Errors are generic and omit synthetic traceback/configuration detail; normal operation remains functional.",
}


def _json_body(response):
    if response["content_type"] != "application/json":
        return None
    try:
        value = json.loads(response["body"])
        return value if isinstance(value, dict) else None
    except ValueError:
        return None


def classify(check, probe, normal):
    """Return exposed/safe/unknown from content and legitimate-use controls."""
    if check == Check.AUTHORIZATION:
        expected = {"id": "record-bob", "owner": "bob", "value": "SYNTHETIC-BOB-ONLY"}
        if normal["status"] != 200 or _json_body(normal) != expected:
            return "unknown"
        if probe["status"] == 200 and _json_body(probe) == expected:
            return "exposed"
        if probe["status"] == 403 and _json_body(probe) == {"error": "forbidden"}:
            return "safe"
    elif check == Check.REFLECTION:
        if normal != {"status": 200, "content_type": "text/html", "body": "<p>Hello LABPROOF-NORMAL</p>"}:
            return "unknown"
        if probe["status"] != 200 or probe["content_type"] != "text/html":
            return "unknown"
        if probe["body"] == "<p>Hello <em>LABPROOF-MARKER</em></p>":
            return "exposed"
        if probe["body"] == "<p>Hello &lt;em&gt;LABPROOF-MARKER&lt;/em&gt;</p>":
            return "safe"
    elif check == Check.DISCLOSURE:
        if normal["status"] != 200 or _json_body(normal) != {"result": "SYNTHETIC-OK"}:
            return "unknown"
        if probe["status"] != 500 or probe["content_type"] != "text/plain":
            return "unknown"
        if all(marker in probe["body"] for marker in ("SYNTHETIC Traceback", "SyntheticDatabaseError", "demo_config=training-only")):
            return "exposed"
        if probe["body"] == "Request failed; reference SYNTHETIC-ERROR":
            return "safe"
    return "unknown"


def adjudicate(evidence):
    index = {(e["check_id"], e["variant"], e["control"], e["phase"]): e for e in evidence}
    results = []
    for check in CATALOGUE:
        for variant in VARIANTS:
            own = [e for e in evidence if e["check_id"] == check.value and e["variant"] == variant]
            relevant = list(own)
            observations = []
            for phase in PHASES:
                probe = index.get((check.value, variant, "probe", phase))
                normal = index.get((check.value, variant, "normal", phase))
                observations.append(classify(check, probe["response"], normal["response"]) if probe and normal else "unknown")
            status, reason = "inconclusive", "Missing, ambiguous or inconsistent response/control evidence."
            if not own:
                status, reason = "not_tested", "No observations collected for this check and variant."
            elif observations == ["safe", "safe"]:
                status, reason = "rejected", "Both replay passes satisfy the invariant while normal controls remain functional; limited to this check."
            elif observations == ["exposed", "exposed"]:
                safe_twin = []
                for phase in PHASES:
                    p = index.get((check.value, "corrected", "probe", phase))
                    n = index.get((check.value, "corrected", "normal", phase))
                    safe_twin.append(classify(check, p["response"], n["response"]) if p and n else "unknown")
                    if p and p not in relevant:
                        relevant.append(p)
                    if n and n not in relevant:
                        relevant.append(n)
                if safe_twin == ["safe", "safe"]:
                    status, reason = "confirmed", "Synthetic disclosure/reflection reproduced in both replay passes; corrected and legitimate-use controls satisfy the invariant."
                else:
                    reason = "Exposed response observed, but corrected comparison evidence does not establish the control."
            results.append({
                "id": f"finding_{check.value}_{variant}", "title": TITLES[check],
                "check_id": check.value, "variant": variant, "status": status,
                "expected": EXPECTED[check], "observed": reason,
                "evidence_ids": [e["id"] for e in relevant],
            })
    return results


def replay_narrative(status, findings):
    """Canonical replay wording, shared by export and read-only verification."""
    counts = {label: sum(f["status"] == label for f in findings) for label in ("confirmed", "rejected", "inconclusive", "not_tested")}
    return {
        "title": "LabProof synthetic evidence replay",
        "summary": f"Synthetic replay ({status}): " + ", ".join(f"{v} {k}" for k, v in counts.items()) + ". Not a live security assessment.",
        "limitations": list(LIMITATIONS),
    }


def build_report(run_id, status, evidence, usage):
    findings = adjudicate(evidence)
    return {
        "project_id": "labproof", "run_id": run_id, "mode": "replay", "status": status,
        **replay_narrative(status, findings), "findings": findings, "evidence": evidence,
        "public_remediation_claims": [], "usage": usage,
        "provenance": {"decisions": "scripted_catalogue", "observations": "synthetic_fixture", "verification": "same_snapshot_replay", "model": "not_used"},
    }
