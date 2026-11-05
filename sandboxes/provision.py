"""Build only reviewed local images; run during explicit provisioning, never assessment.

Run with isolated Python inside Debian. Dependencies/base downloads require prior
user approval. No fixture is executed by this script outside Docker image builds.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PACKS = {"python": ("python:3.13-slim", "python"),
         "typescript": ("node:24-slim", "node"),
         "c": ("gcc:14", "c"), "rust": ("rust:1-bookworm", "rust")}


def docker(*args):
    result = subprocess.run(["/usr/bin/docker", "--host", "unix:///var/run/docker.sock", *args],
                            cwd="/tmp", env={"PATH": "/usr/bin:/bin", "HOME": "/root"},
                            capture_output=True, text=True, timeout=600, check=True)
    return result.stdout.strip()


def tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def main():
    root, destination = map(lambda p: Path(p).resolve(), sys.argv[1:])
    result = {"schema_version": "local-provisioning-1", "packs": {}}
    for pack, (base, folder) in PACKS.items():
        # Base tags are resolved once at provisioning; all builds use the digest.
        inspected = json.loads(docker("image", "inspect", base))[0]
        digest = inspected["RepoDigests"][0]
        if not re.fullmatch(r"[a-z0-9./:_-]+@sha256:[a-f0-9]{64}", digest):
            raise ValueError("Unpinned base")
        build_log = docker("build", "--network=none", "--pull=false", "--build-arg", f"BASE_IMAGE={digest}",
               "-f", str(root / "sandboxes" / folder / "Dockerfile"),
               "-t", f"labproof-{pack}:local", str(root))
        log = destination.with_name(destination.stem + f"-{pack}-build.txt")
        with log.open("x", encoding="utf-8") as stream:
            stream.write(build_log)
        image = json.loads(docker("image", "inspect", f"labproof-{pack}:local"))[0]
        result["packs"][pack] = {"image_id": image["Id"], "base_digest": digest,
            "fixture_sha256": tree_hash(root / "src/labproof/fixtures/packs" / pack),
            "worker_sha256": tree_hash(root / "sandboxes" / folder)}
        print(pack, image["Id"], flush=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)


if __name__ == "__main__":
    main()
