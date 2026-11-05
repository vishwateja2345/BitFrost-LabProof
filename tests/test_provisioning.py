"""Identity/provisioner unit tests; no Docker calls or runtime acceptance."""
from copy import deepcopy
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess

import pytest

from labproof.contracts import ValidationError, canonical, parse_json
from labproof.provisioning import (build_identities, installed_identities,
                                  verify_installed_identities, source_paths)

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path):
    target = tmp_path / "project"
    shutil.copytree(PROJECT / "src" / "labproof", target / "src" / "labproof",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(PROJECT / "sandboxes", target / "sandboxes",
                    ignore=shutil.ignore_patterns("__pycache__"))
    return target


def provisioner():
    spec = importlib.util.spec_from_file_location("reviewed_provision_v2", PROJECT / "sandboxes" / "provision_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_separate_recipe_source_oracle_and_host_identities(project):
    package = project / "src" / "labproof"
    before = build_identities(project, "python")
    oracle = package / "fixtures/packs/python/oracle.host-only.json"
    oracle.write_bytes(oracle.read_bytes() + b"\n")
    after = build_identities(project, "python")
    assert before["source"] == after["source"]
    assert before["worker"] == after["worker"]
    assert before["oracle"] != after["oracle"]
    host = package / "adapters/observations.py"
    host.write_bytes(host.read_bytes() + b"\n")
    assert after["adapter"] != build_identities(project, "python")["adapter"]


@pytest.mark.parametrize("pack", ("python", "typescript", "c", "rust"))
def test_source_manifest_matches_fixed_recipe(pack, project):
    identity = build_identities(project, pack)
    names = [row["path"] for row in identity["source"]["files"]]
    assert names == list(source_paths(pack))
    assert not any("host-only" in name for name in names)
    assert len(names) == (8 if pack in ("python", "typescript") else 4)
    assert (identity["dependency_lock"] is not None) == (pack == "rust")


def test_extra_directory_copy_input_rejected(project):
    extra = project / "src/labproof/fixtures/packs/python/alpha/secret.host-only.json"
    extra.write_text("{}")
    with pytest.raises(ValidationError, match="Unexpected worker-visible"):
        build_identities(project, "python")


def test_changed_installed_bytes_blocked(project):
    package = project / "src/labproof"
    identities = installed_identities(package, "python")
    provenance = {kind + "_sha256": identities[kind]["sha256"] for kind in identities}
    assert verify_installed_identities(package, "python", provenance) == provenance
    source = package / "fixtures/packs/python/alpha/authz.py"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValidationError, match="Installed source"):
        verify_installed_identities(package, "python", provenance)


@pytest.mark.parametrize("base", ("python:latest", "node@sha256:" + "a" * 64,
                                    "evil/python@sha256:" + "a" * 64))
def test_reject_unreviewed_pin(base):
    with pytest.raises(ValidationError):
        provisioner().validate_pins({"schema_version": "reviewed-local-bases-1", "bases": {"python": base}})


def test_mock_build_records_separate_identities_and_no_pull(project, tmp_path, monkeypatch):
    module = provisioner()
    base = "python@sha256:" + "a" * 64
    calls = []
    def docker(*args):
        calls.append(args)
        if args[:2] == ("image", "inspect"):
            return canonical([{"Id": "sha256:" + "b" * 64, "RepoDigests": [base]}]), b""
        context = Path(args[-1])
        assert context != project
        files = [p.relative_to(context).as_posix() for p in context.rglob("*") if p.is_file()]
        assert len(files) == 10
        assert not any("host-only" in name or "provision" in name for name in files)
        return b"invented build log", b""
    monkeypatch.setattr(module, "docker", docker)
    output = tmp_path / "record"
    record = module.provision(project, {"schema_version": "reviewed-local-bases-1", "bases": {"python": base}}, output)
    entry = record["profiles"]["python-invariants-experiment-2"]
    identities = build_identities(project, "python")
    for kind in ("source", "oracle", "worker", "adapter"):
        assert entry[kind + "_sha256"] == identities[kind]["sha256"]
    assert entry["binary_sha256"] is None
    build = next(call for call in calls if call[0] == "build")
    assert "--pull=false" in build and "--network=none" in build
    assert not any(call[0] in ("pull", "run", "exec") for call in calls)
    journal = parse_json((output / "build-journal.json").read_bytes())
    assert journal["status"] == "built_not_runtime_accepted"
    count = len(calls)
    with pytest.raises(ValidationError, match="must be new"):
        module.provision(project, {"schema_version": "reviewed-local-bases-1", "bases": {"python": base}}, output)
    assert len(calls) == count


@pytest.mark.parametrize("size,returncode,raises", [(20, 0, False), (20, 1, True), (2_000_001, 0, True)])
def test_build_supervision_bounds_output_and_clears_environment(monkeypatch, size, returncode, raises):
    module = provisioner()
    class Process:
        def __init__(self, command, **kwargs):
            assert kwargs["stdin"] == subprocess.DEVNULL
            assert kwargs["env"]["DOCKER_CONFIG"] == kwargs["cwd"]
            assert set(kwargs["env"]) == {"PATH", "HOME", "DOCKER_CONFIG"}
            assert command[0] == "/usr/bin/docker" and "--host" in command
            self.stdout = io.BytesIO(b"x" * size)
            self.returncode = returncode
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stdout.close()
        def poll(self):
            return self.returncode
        def wait(self, timeout):
            return self.returncode
        def kill(self):
            self.returncode = -9
    monkeypatch.setattr(module.subprocess, "Popen", Process)
    if raises:
        with pytest.raises(subprocess.CalledProcessError) as caught:
            module.docker("image", "inspect", "synthetic")
        assert len(caught.value.stdout) <= 2_000_000
    else:
        assert module.docker("image", "inspect", "synthetic") == (b"x" * size, b"")


def test_failed_build_retains_failure_no_provision_record(project, tmp_path, monkeypatch):
    module = provisioner()
    base = "python@sha256:" + "a" * 64
    def docker(*args):
        if args[0] == "build":
            raise subprocess.CalledProcessError(1, args, output=b"failure", stderr=b"diagnostic")
        return canonical([{"RepoDigests": [base]}]), b""
    monkeypatch.setattr(module, "docker", docker)
    output = tmp_path / "failed"
    with pytest.raises(subprocess.CalledProcessError):
        module.provision(project, {"schema_version": "reviewed-local-bases-1", "bases": {"python": base}}, output)
    assert not (output / "local-provisioning-v2.json").exists()
    assert (output / "failed-stderr.txt").read_bytes() == b"diagnostic"
    journal = parse_json((output / "build-journal.json").read_bytes())
    assert journal["status"] == "incomplete" and journal["error_type"] == "CalledProcessError"
