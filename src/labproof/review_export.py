"""One-use approval for releasing a verified local evidence bundle."""
from contextlib import closing, contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time

from .contracts import ID_RE, SHA_RE, ValidationError, canonical, check_no_links, parse_json, read_safe, require, validate_manifest
from .export_viewer import export_viewer

KEY_ENV = "LABPROOF_REVIEW_KEY"
SCHEMA = "labproof-review-approval-1"
ACTION = "export-viewer"
PHASE = "review"
MAX_APPROVAL_BYTES = 4096
MAX_TTL = 3600
CLAIM_FIELDS = {"schema_version", "task_id", "action", "phase", "args_sha256", "expires_at", "nonce"}


def load_key(environ):
    value = environ.get(KEY_ENV, "")
    require(SHA_RE.fullmatch(value) is not None, f"Set {KEY_ENV} to 32 random bytes encoded as lowercase hex")
    return bytes.fromhex(value)


def read_approval(path):
    path = Path(path).absolute()
    check_no_links(path)
    require(path.is_file(), "Approval must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_APPROVAL_BYTES + 1)
    require(len(raw) <= MAX_APPROVAL_BYTES, "Approval file exceeds 4 KiB")
    return parse_json(raw)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _signature(key, claims):
    require(isinstance(key, bytes) and len(key) == 32, "Review signing key must be 32 bytes")
    return hmac.digest(key, canonical(claims), "sha256").hex()


def _valid_digest(value):
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def _claims(key, approval):
    require(isinstance(approval, dict) and set(approval) == {"claims", "signature"}, "Invalid approval envelope")
    claims = approval["claims"]
    signature = approval["signature"]
    require(isinstance(claims, dict) and set(claims) == CLAIM_FIELDS, "Invalid approval claims")
    require(claims["schema_version"] == SCHEMA and claims["action"] == ACTION and claims["phase"] == PHASE,
            "Approval is for an unsupported action or phase")
    require(isinstance(claims["task_id"], str) and ID_RE.fullmatch(claims["task_id"]) is not None, "Invalid approval task ID")
    require(_valid_digest(claims["nonce"]) and _valid_digest(claims["args_sha256"]), "Invalid approval identifiers")
    require(type(claims["expires_at"]) is int and 0 < claims["expires_at"] < 2**63, "Invalid approval expiry")
    require(_valid_digest(signature) and hmac.compare_digest(_signature(key, claims), signature), "Invalid approval signature")
    return claims


def _paths(root, output, ledger, task):
    require(isinstance(task, str) and ID_RE.fullmatch(task) is not None, "Invalid review task ID")
    root, output, ledger = (Path(path).absolute() for path in (root, output, ledger))
    require(all(".." not in path.parts for path in (root, output, ledger)), "Use paths without parent traversal")
    require(not output.is_relative_to(root) and not ledger.is_relative_to(root) and output != ledger,
            "Output and ledger must be distinct and outside the source run")
    check_no_links(output.parent)
    require(not output.exists() and not output.is_symlink(), "Export output already exists")
    return root, output, ledger


def _bound_arguments(root, output, manifest):
    return _sha(canonical({"directory": str(root), "output": str(output), "manifest_sha256": _sha(manifest)}))


@contextmanager
def _ledger(path, *, create=False):
    path = Path(path).absolute()
    if create:
        check_no_links(path.parent)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
    check_no_links(path)
    require(path.is_file(), "Approval ledger must be a regular file")
    if os.name == "posix":
        require(path.stat().st_mode & 0o022 == 0, "Approval ledger must not be writable by group or others")
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if create:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS review_approvals (
                        nonce TEXT PRIMARY KEY,
                        approval_sha256 TEXT NOT NULL,
                        expires_at INTEGER NOT NULL,
                        state TEXT NOT NULL CHECK(state IN ('approved', 'used', 'revoked'))
                    )
                """)
            yield connection
    except sqlite3.Error as exc:
        raise ValidationError("Approval ledger is unavailable or invalid") from exc


def approve_export(root, output, *, task, ledger, key, ttl=300):
    require(type(ttl) is int and 1 <= ttl <= MAX_TTL, "Approval TTL must be between 1 and 3600 seconds")
    root, output, ledger = _paths(root, output, ledger, task)
    raw = read_safe(root, "manifest.json")
    manifest = parse_json(raw)
    validate_manifest(manifest)
    require(manifest["mode"] in ("replay", "local"), "Approval supports replay and local runs")
    with _ledger(ledger, create=True) as connection:
        claims = {
            "schema_version": SCHEMA, "task_id": task, "action": ACTION, "phase": PHASE,
            "args_sha256": _bound_arguments(root, output, raw),
            "expires_at": int(time.time()) + ttl, "nonce": secrets.token_hex(32),
        }
        approval = {"claims": claims, "signature": _signature(key, claims)}
        connection.execute(
            "INSERT INTO review_approvals VALUES (?, ?, ?, 'approved')",
            (claims["nonce"], _sha(canonical(approval)), claims["expires_at"]),
        )
    return approval


def _transition(ledger, approval, claims, state):
    with _ledger(ledger) as connection:
        if state == "used":
            require(int(time.time()) < claims["expires_at"], "Export approval expired")
        changed = connection.execute(
            "UPDATE review_approvals SET state = ? WHERE nonce = ? AND approval_sha256 = ? AND state = 'approved'",
            (state, claims["nonce"], _sha(canonical(approval))),
        )
        require(changed.rowcount == 1, "Approval already used, revoked, or absent from this ledger")


def redeem_export(root, output, *, task, ledger, key, approval):
    claims = _claims(key, approval)
    require(claims["task_id"] == task, "Approval belongs to a different task")
    root, output, ledger = _paths(root, output, ledger, task)
    raw = read_safe(root, "manifest.json")
    require(hmac.compare_digest(claims["args_sha256"], _bound_arguments(root, output, raw)),
            "Approval does not match the source manifest and export destination")
    _transition(ledger, approval, claims, "used")
    return export_viewer([root], output, expected_manifest=raw)


def revoke_export(*, ledger, key, approval):
    claims = _claims(key, approval)
    _transition(ledger, approval, claims, "revoked")
    return {"task_id": claims["task_id"], "status": "revoked"}
