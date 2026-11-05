"""Non-executing identity derivation for reviewed fixed v2 worker recipes.

These hashes are host assertions, not runtime acceptance. Source manifests use
explicit recipe inputs; host-only oracles never enter the worker source digest.
"""
from hashlib import sha256
from pathlib import Path

from .contracts import canonical, check_no_links, read_safe, require
from .local_profiles import default_profile, VARIANTS

EXTENSIONS = {"python": "py", "typescript": "ts", "c": "c", "rust": "rs"}
FOLDERS = {"python": "python", "typescript": "node", "c": "c", "rust": "rust"}
WORKERS = {
    "python": ("Dockerfile", "worker.py"),
    "typescript": ("Dockerfile", "worker.mjs", "observe.test.mjs"),
    "c": ("Dockerfile", "worker.c", "response.h"),
    "rust": ("Dockerfile", "Cargo.toml", "Cargo.lock", "src/main.rs"),
}


def source_paths(pack_id):
    default_profile(pack_id)
    names = [f"{variant}/authz.{EXTENSIONS[pack_id]}" for variant in VARIANTS]
    if pack_id in ("python", "typescript"):
        names.extend(f"{variant}/inputs.json" for variant in VARIANTS)
    return tuple(sorted(names))


def file_inventory(root, paths):
    """Hash a nonempty explicit set; length framing comes from canonical JSON."""
    root = Path(root).absolute()
    check_no_links(root)
    paths = tuple(paths)
    require(bool(paths) and len(paths) == len(set(paths)), "Empty or duplicate identity inputs")
    rows = []
    for name in sorted(paths):
        raw = read_safe(root, name)
        rows.append({"path": name, "bytes": len(raw), "sha256": sha256(raw).hexdigest()})
    return {"files": rows, "sha256": sha256(canonical(rows)).hexdigest()}


def installed_identities(package, pack_id):
    """Bind shipped fixture bytes, oracle and all maintained host Python code.

    Bytecode is excluded; Python files below the fixture tree are never imported.
    Binding all host modules includes the actual embedded grader, not just its
    explanatory oracle JSON. Adding host code intentionally invalidates this ID.
    """
    default_profile(pack_id)
    package = Path(package).absolute()
    check_no_links(package)
    host_paths = []
    for path in sorted(package.rglob("*")):
        check_no_links(path)
        relative = path.relative_to(package)
        if path.is_file() and path.suffix == ".py" and relative.parts[0] != "fixtures":
            host_paths.append(relative.as_posix())
    fixtures = package / "fixtures" / "packs" / pack_id
    expected = source_paths(pack_id)
    if pack_id in ("python", "typescript"):
        # These two recipes COPY whole variant directories, so extra files are
        # build inputs too. Reject them instead of silently omitting their hash.
        actual = []
        for variant in VARIANTS:
            for path in (fixtures / variant).rglob("*"):
                check_no_links(path)
                require(path.is_dir() or path.is_file(), "Nonregular worker input")
                if path.is_file():
                    actual.append(path.relative_to(fixtures).as_posix())
        require(sorted(actual) == list(expected), "Unexpected worker-visible fixture files")
    return {
        "source": file_inventory(fixtures, expected),
        "oracle": file_inventory(fixtures, ("oracle.host-only.json",)),
        "adapter": file_inventory(package, host_paths),
    }


def build_identities(project, pack_id):
    """Derive identities before a build; does not inspect or start a runtime."""
    project = Path(project).absolute()
    identities = installed_identities(project / "src" / "labproof", pack_id)
    worker = project / "sandboxes" / FOLDERS[pack_id]
    identities["worker"] = file_inventory(worker, WORKERS[pack_id])
    identities["dependency_lock"] = (file_inventory(worker, ("Cargo.lock",))
                                      if pack_id == "rust" else None)
    return identities


def verify_installed_identities(package, pack_id, provenance):
    """Reject stale installed host/fixture bytes before opening a live session."""
    identities = installed_identities(package, pack_id)
    for kind in ("source", "oracle", "adapter"):
        require(provenance[kind + "_sha256"] == identities[kind]["sha256"],
                "Installed " + kind + " differs from trusted v2 provisioning")
    return provenance
