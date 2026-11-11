# Approved export of verified evidence

`review-export` gives a trusted local operator a way to approve one viewer export. The approval binds the task ID, the source run's absolute path and exact manifest bytes, the output path, the action, and the expiry. When provided, it also binds the absolute brief directory and exact `brief.json` bytes. A SQLite ledger serializes use and revocation, including across separate processes. The command consumes the approval before invoking the verifier and creating the JSON bundle.

From the repository root, with LabProof installed:

```bash
mkdir -p runs
work="$(mktemp -d "$PWD/runs/approved-review.XXXXXX")"
export LABPROOF_REVIEW_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

(umask 077
python -m labproof review-export --ledger "$work/approvals.sqlite3" approve evidence/local-python-01 \
   --task python-review --output "$work/review.json" > "$work/approval.json"
)

python -m labproof review-export --ledger "$work/approvals.sqlite3" redeem evidence/local-python-01 \
  --task python-review --output "$work/review.json" --approval "$work/approval.json"
```

Import the resulting `review.json` in the evidence workspace. The default lifetime is 300 seconds. Set `--ttl` on approval for a lifetime between 1 and 3,600 seconds. Use the same key and ledger for redemption. To include a brief, give the same `--brief evidence/live-brief-03/relay` option to both commands. Use `revoke --approval "$work/approval.json"` with the same ledger to revoke an unused approval.

Keep the key, ledger, and approval file under the trusted operator account. Use a local filesystem and a trusted host clock. If the verifier or file write fails after consumption, issue a fresh approval after resolving the failure. Copying or restoring the ledger to an earlier state can restore earlier approvals. The ordinary `export-viewer` command remains available to operators. Deployments that delegate this operation must give callers access only through the approved workflow.

## Research basis

The supplied OMEGA v18.1 study used host-issued, single-use capabilities and in-memory replay state. The archived checksums matched, and an offline rerun reproduced the recorded decisions and invariance checks. Its gate accepted zero of 2,700 unauthorized proposals and rejected zero of 300 valid proposals. Those counts describe the study's deterministic fixtures. LabProof applies the pattern at an actual file-export boundary and tests concurrent use, revocation, expiry, and manifest changes against its own exporter.

OMEGA v15's negative result informs how the workspace presents exported evidence. A signed approval authenticates the permission to export. The artifact verifier checks internal consistency, while independence and authenticity of the underlying observations remain separate questions.

The design follows OWASP's guidance to enforce authorization at the downstream operation. Fine-grained action bindings have precedent in RFC 9396. SQLite transactions provide the single-writer boundary for the ledger. AgentDojo's model-based evaluation is a separate line of evidence beyond the supplied conformance study.

[OWASP Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/) · [RFC 9396](https://www.rfc-editor.org/rfc/rfc9396.html) · [SQLite transaction semantics](https://www.sqlite.org/lang_transaction.html) · [AgentDojo paper](https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html)
