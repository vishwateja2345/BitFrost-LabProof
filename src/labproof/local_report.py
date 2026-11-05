"""Versioned local report derivation; no runtime calls or fixture execution."""
from .adapters import adjudicate_observations

LOCAL_LIMITATIONS = [
    "Purpose-built synthetic authorization fixtures only; not an assessment of external software.",
    "Findings require repeated observations and corrected/normal controls; static signals alone do not confirm flaws.",
    "Verification uses fresh containers and host-side rules, not a separate human or model auditor.",
    "Retained runtime checks describe tested controls, not a guarantee against container escapes.",
    "Unsigned artifacts establish internal consistency, not source authenticity or proof that execution occurred.",
    "No model, live retrieval, autonomous exploration, or public remediation claims are used.",
]
LOCAL_PROVENANCE = {
    "decisions": "fixed_catalogue", "observations": "local_container",
    "verification": "fresh_container_reexecution", "adjudication": "host_control_rules_v1",
    "model": "not_used",
}


def build_local_report(run_id, status, pack_id, records, executions):
    findings = adjudicate_observations(records, pack_id=pack_id)
    confirmed = sum(f["status"] == "confirmed" for f in findings)
    evidence = [{"id": r["id"], "title": f"{r['observation']['operation_id']} {r['observation']['variant']} ({r['phase']})",
                 "content": r["observation"]["raw_text"],
                 "artifact_path": f"evidence/{r['id']}.json", "record": r}
                for r in records]
    return {"schema_version": "local-report-1", "project_id": "labproof", "run_id": run_id,
            "mode": "local", "status": status, "pack_id": pack_id,
            "title": f"LabProof local {pack_id} synthetic comparison",
            "summary": f"{status}: {len(records)} retained observations; {confirmed} scoped confirmed findings.",
            "limitations": list(LOCAL_LIMITATIONS), "provenance": dict(LOCAL_PROVENANCE),
            "public_remediation_claims": [], "evidence": evidence, "findings": findings,
            "usage": {"tool_attempts": len(executions), "model_calls": 0,
                      "model_usage": None, "model_usage_status": "not_applicable_deterministic",
                      "output_bytes": sum(e["output_bytes"] for e in executions)}}
