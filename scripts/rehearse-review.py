"""Run the saved evidence and approval walkthrough using local artifacts."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNS = [f"evidence/{name}" for name in ("local-python-01", "local-typescript-01", "local-rust-01", "local-c-03")]
RELAY = "evidence/live-brief-03/relay"


def rehearse(output):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), LABPROOF_REVIEW_KEY=secrets.token_hex(32))

    def cli(*arguments, denial=None):
        result = subprocess.run([sys.executable, "-m", "labproof", *map(str, arguments)],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        if denial:
            if result.returncode != 1 or denial not in result.stderr:
                raise RuntimeError(f"Expected denial: {denial}")
            return
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "LabProof command failed")
        return json.loads(result.stdout)

    for run in RUNS:
        cli("verify-artifacts", run)
    briefs = {route: cli("verify-brief", RUNS[0], f"evidence/live-brief-03/{route}")
              for route in ("direct", "relay")}
    bundle = output / "review.json"
    cli("export-viewer", *RUNS, "--brief", RELAY, "--output", bundle)
    actual = json.loads(bundle.read_bytes())
    saved = json.loads((ROOT / "viewer/public/review.json").read_bytes())
    if any(actual[key] != saved[key] for key in ("runs", "remediation")):
        raise RuntimeError("Saved viewer data differs from the verified export")

    review = ("review-export", "--ledger", output / "approvals.sqlite3")
    approved = output / "approved.json"
    options = (RUNS[0], "--task", "demo-review", "--brief", RELAY, "--output", approved)
    token = output / "approval.json"
    token.write_text(json.dumps(cli(*review, "approve", *options)), encoding="utf-8")
    cli(*review, "redeem", *options, "--approval", token)
    approved.rename(output / "verified-approval-export.json")
    cli(*review, "redeem", *options, "--approval", token, denial="Approval already used")
    token.write_text(json.dumps(cli(*review, "approve", *options)), encoding="utf-8")
    if cli(*review, "close-task", "--task", "demo-review")["revoked"] != 1:
        raise RuntimeError("Task closure did not revoke the pending approval")
    cli(*review, "redeem", *options, "--approval", token, denial="Review task is closed")
    cli(*review, "approve", *options, denial="Review task is closed")

    return {"status": "passed", "runs": len(RUNS), "viewer_bundle": str(bundle),
            "saved_recommendations": {route: brief["recommendations"] for route, brief in briefs.items()},
            "approval_checks": ["approved export", "reuse denied", "closed task denied"]}


if __name__ == "__main__":
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    try:
        output = Path(tempfile.mkdtemp(prefix="review-rehearsal.", dir=runs))
        print(json.dumps(rehearse(output), indent=2))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        sys.exit(f"Rehearsal failed: {exc}")
