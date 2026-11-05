"""Small embedded contract validator; no sibling-package dependency."""
from datetime import datetime
import json
from pathlib import Path
import re
import stat

MAX_FILE_BYTES = 2_000_000
MAX_RUN_BYTES = 8_000_000
MAX_FILES = 128
ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(_):
    raise ValidationError("Nonfinite JSON number")


def parse_json(raw: bytes):
    require(len(raw) <= MAX_FILE_BYTES, "JSON size limit exceeded")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValidationError(f"Invalid JSON: {exc}") from exc


def timestamp(value):
    require(isinstance(value, str), "Timestamp must be a string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require("T" in value and result.tzinfo is not None, "Timestamp needs time and timezone")
        return result
    except ValueError as exc:
        raise ValidationError("Invalid timestamp") from exc


def strings(value, label):
    require(isinstance(value, list) and all(isinstance(s, str) for s in value), f"{label} must be a string array")


def safe_relative(value):
    require(isinstance(value, str) and 0 < len(value) <= 240, "Invalid artifact path")
    require(not any(c in value for c in "\\:\x00"), "Unsafe artifact path")
    parts = value.split("/")
    require(all(p not in {"", ".", ".."} and re.fullmatch(r"[A-Za-z0-9_.-]+", p) and not p.endswith((".", " ")) for p in parts), "Unsafe artifact path")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{s}{i}" for s in ("COM", "LPT") for i in range(1, 10)}
    require(all(p.split(".")[0].upper() not in reserved for p in parts), "Reserved artifact path")
    return parts


def check_no_links(path: Path):
    for item in (path, *path.parents):
        st = item.lstat()
        require(not stat.S_ISLNK(st.st_mode) and not getattr(st, "st_file_attributes", 0) & 0x400, "Symlink/reparse point forbidden")


def read_safe(root: Path, relative: str) -> bytes:
    parts = safe_relative(relative)
    target = root.joinpath(*parts)
    check_no_links(target)
    require(target.is_file(), "Artifact is not a regular file")
    require(target.stat().st_size <= MAX_FILE_BYTES, "Artifact size limit exceeded")
    with target.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    require(len(raw) <= MAX_FILE_BYTES, "Artifact grew beyond size limit")
    return raw


def validate_manifest(m):
    require(isinstance(m, dict), "Manifest must be an object")
    fields = {"schema_version", "project_id", "run_id", "mode", "status", "created_at", "artifacts", "limitations"}
    require(set(m) == fields, "Unexpected or missing manifest fields")
    require(m["schema_version"] == "1.0" and m["project_id"] == "labproof", "Unsupported schema/project")
    require(isinstance(m["run_id"], str) and ID_RE.fullmatch(m["run_id"]), "Invalid run ID")
    require(m["mode"] in ("replay", "local", "live"), "Invalid mode")
    require(m["status"] in ("completed", "incomplete", "blocked", "failed", "cancelled"), "Invalid status")
    timestamp(m["created_at"])
    strings(m["limitations"], "limitations")
    require(isinstance(m["artifacts"], list) and 1 <= len(m["artifacts"]) <= MAX_FILES, "Invalid artifact list")
    seen = set()
    total = 0
    for entry in m["artifacts"]:
        require(isinstance(entry, dict) and set(entry) == {"path", "sha256", "bytes"}, "Invalid artifact entry")
        safe_relative(entry["path"])
        require(entry["path"].lower() not in seen and entry["path"].lower() != "manifest.json", "Duplicate/reserved artifact path")
        seen.add(entry["path"].lower())
        require(isinstance(entry["sha256"], str) and SHA_RE.fullmatch(entry["sha256"]), "Invalid digest")
        require(type(entry["bytes"]) is int and 0 <= entry["bytes"] <= MAX_FILE_BYTES, "Invalid artifact size")
        total += entry["bytes"]
    require(total <= MAX_RUN_BYTES, "Run size limit exceeded")
    require({"report.json", "events.jsonl", "errors.jsonl", "config.json"} <= {a["path"] for a in m["artifacts"]}, "Missing required artifacts")
