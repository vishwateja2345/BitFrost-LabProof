"""Explicit fixed-profile provisioning using reviewed, already-local base digests.

Invoke with installed LabProof and isolated Python. Never run as an assessment
step. This builds images, not runtime acceptance. It does not download bases,
install dependencies, run fixtures on the host, or install its output record.
"""
import argparse
from hashlib import sha256
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from uuid import uuid4

from labproof.contracts import canonical, check_no_links, parse_json, read_safe, require
from labproof.engine import write_new
from labproof.local_experiments import validate_provenance
from labproof.local_profiles import default_profile
from labproof.provisioning import build_identities, FOLDERS

BASES = {"python": "python", "typescript": "node", "c": "gcc", "rust": "rust"}


def docker(*args):
    # Build logs are bounded while streaming, not after capture_output has
    # allocated an arbitrary amount. A killed build CLI is not runtime cleanup
    # acceptance; this helper never launches an assessment container.
    with tempfile.TemporaryDirectory(prefix="labproof-build-") as scratch:
        env = {"PATH": "/usr/bin:/bin", "HOME": scratch, "DOCKER_CONFIG": scratch}
        command = ["/usr/bin/docker", "--config", scratch, "--host",
                   "unix:///var/run/docker.sock", *args]
        output, failed, done = bytearray(), threading.Event(), threading.Event()
        with subprocess.Popen(command, cwd=scratch, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0) as proc:
            def drain():
                try:
                    while chunk := proc.stdout.read(4096):
                        room = 2_000_000 - len(output)
                        output.extend(chunk[:room])
                        if len(chunk) > room:
                            failed.set()
                            return
                except (OSError, ValueError):
                    failed.set()
                finally:
                    done.set()
            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            deadline = time.monotonic() + 600
            try:
                while not (proc.poll() is not None and done.is_set()):
                    if failed.is_set():
                        raise subprocess.CalledProcessError(-1, command, output=bytes(output))
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired(command, 600, output=bytes(output))
                    time.sleep(0.02)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=10)
                reader.join(timeout=10)
            if reader.is_alive() or failed.is_set():
                raise subprocess.CalledProcessError(-1, command, output=bytes(output))
            if proc.returncode:
                raise subprocess.CalledProcessError(proc.returncode, command, output=bytes(output))
        return bytes(output), b""


def validate_pins(pins):
    require(type(pins) is dict and set(pins) == {"schema_version", "bases"}
            and pins["schema_version"] == "reviewed-local-bases-1", "Invalid base pin document")
    require(type(pins["bases"]) is dict and 0 < len(pins["bases"]) <= 4, "Invalid base selection")
    for pack, digest in pins["bases"].items():
        default_profile(pack)
        require(type(digest) is str and re.fullmatch(
            r"(?:docker\.io/library/)?" + BASES[pack] + r"@sha256:[a-f0-9]{64}", digest),
            "Base must be a reviewed exact official image digest")
    return pins


def stage_context(project, pack, identities, context):
    """Copy only measured worker inputs into a private Docker build context."""
    groups = ((project / "sandboxes" / FOLDERS[pack],
               context / "sandboxes" / FOLDERS[pack], identities["worker"]),
              (project / "src/labproof/fixtures/packs" / pack,
               context / "src/labproof/fixtures/packs" / pack, identities["source"]))
    for source, destination, inventory in groups:
        for row in inventory["files"]:
            raw = read_safe(source, row["path"])
            require(len(raw) == row["bytes"] and sha256(raw).hexdigest() == row["sha256"],
                    "Build input changed before staging")
            target = destination / row["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            write_new(target, raw)


def provision(project, pins, output):
    project, output = Path(project).absolute(), Path(output).absolute()
    check_no_links(project)
    check_no_links(output.parent)
    pins = validate_pins(pins)
    require(not output.exists(), "Provisioning output must be new")
    # Compute all identities before creating output or invoking Docker.
    before = {pack: build_identities(project, pack) for pack in pins["bases"]}
    for pack in before:
        installed = build_identities(project, pack)
        require(installed == before[pack], "Source changed during identity collection")
    output.mkdir()
    journal = {"schema_version": "provisioning-build-journal-2", "status": "incomplete",
               "pins": pins, "identities": before, "builds": [],
               "limitations": ["Build identity is not containment or runtime acceptance.",
                               "Compiler and binary fields remain unknown for these legacy recipes."]}
    record = {"schema_version": "local-profiles-provisioning-2", "profiles": {}}
    try:
        for pack, base in pins["bases"].items():
            # Inspect the digest, never resolve a mutable tag or pull an image.
            raw, _ = docker("image", "inspect", base)
            image = parse_json(raw)
            require(type(image) is list and len(image) == 1
                    and base in image[0].get("RepoDigests", []), "Reviewed base absent locally")
            tag = "labproof-" + pack + "-v2:" + uuid4().hex
            attempt = {"pack_id": pack, "tag": tag, "status": "attempted", "image_id": None}
            journal["builds"].append(attempt)
            write_new(output / (pack + "-attempt.json"), canonical(attempt))
            with tempfile.TemporaryDirectory(prefix="labproof-build-inputs-") as scratch:
                context = Path(scratch)
                stage_context(project, pack, before[pack], context)
                stdout, stderr = docker("build", "--network=none", "--pull=false", "--build-arg",
                                        "BASE_IMAGE=" + base, "-f",
                                        str(context / "sandboxes" / FOLDERS[pack] / "Dockerfile"),
                                        "-t", tag, str(context))
            write_new(output / (pack + "-stdout.txt"), stdout)
            write_new(output / (pack + "-stderr.txt"), stderr)
            raw, _ = docker("image", "inspect", tag)
            image = parse_json(raw)
            require(type(image) is list and len(image) == 1, "Invalid built image metadata")
            identities = build_identities(project, pack)
            require(identities == before[pack], "Source changed during build")
            entry = {"schema_version": "local-provisioning-2", "image_id": image[0]["Id"],
                     "base_digest": base,
                     **{kind + "_sha256": identities[kind]["sha256"]
                        for kind in ("source", "oracle", "worker", "adapter")},
                     "dependency_lock_sha256": (None if identities["dependency_lock"] is None
                                                else identities["dependency_lock"]["sha256"]),
                     "compiler_version": None, "compiler_flags": None, "binary_sha256": None}
            validate_provenance(entry)
            record["profiles"][default_profile(pack).operation_id + "-experiment-2"] = entry
            attempt.update(status="built", image_id=entry["image_id"])
        write_new(output / "local-provisioning-v2.json", canonical(record))
        journal["status"] = "built_not_runtime_accepted"
        return record
    except (Exception, KeyboardInterrupt) as error:
        journal["error_type"] = type(error).__name__
        if isinstance(error, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            for name, raw in (("failed-stdout.txt", error.stdout), ("failed-stderr.txt", error.stderr)):
                if isinstance(raw, bytes):
                    write_new(output / name, raw[:2_000_000])
        raise
    finally:
        write_new(output / "build-journal.json", canonical(journal))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--pins", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pins_path = args.pins.absolute()
    provision(args.project, parse_json(read_safe(pins_path.parent, pins_path.name)), args.output)


if __name__ == "__main__":
    main()
