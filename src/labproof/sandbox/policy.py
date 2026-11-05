"""Trusted controller command planning, not a second language registry.

Only packs.REGISTRY validates model requests. No reviewed launch adapters are
provisioned. These immutable plans are host-internal testable building blocks;
SandboxRuntime deliberately cannot execute them before independent acceptance.
"""
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
import os
import re
from types import MappingProxyType

from ..contracts import canonical


class SandboxPolicyError(ValueError):
    pass


def _winget_docker_cli():
    # Fixed WinGet layout under the account's own profile; never PATH or caller input.
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "Microsoft", "WinGet", "Packages",
                        "Docker.DockerCLI_Microsoft.Winget.Source_8wekyb3d8bbwe", "docker", "docker.exe")


# Deliberately not PATH discovery, DOCKER_HOST, a context, or caller configuration.
REVIEWED_CONTROLLERS = MappingProxyType({
    "windows": (
        _winget_docker_cli(),
        "npipe:////./pipe/docker_engine",
        MappingProxyType({"SystemRoot": r"C:\Windows", "WINDIR": r"C:\Windows", "PATH": r"C:\Windows\System32"})),
    "linux": ("/usr/bin/docker", "unix:///var/run/docker.sock",
              MappingProxyType({"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"})),
})
DOCKER_EXECUTABLE, DOCKER_ENDPOINT, REVIEWED_ENVIRONMENT = REVIEWED_CONTROLLERS[
    "windows" if os.name == "nt" else "linux"]
_IMAGE = re.compile(r"sha256:[a-f0-9]{64}")
_ID = re.compile(r"[a-z][a-z0-9_.-]{0,79}")
_WORKER = re.compile(r"labproof-[a-f0-9]{32}")


@dataclass(frozen=True)
class SandboxLimits:
    wall_seconds: float = 15.0
    cleanup_seconds: float = 3.0
    output_bytes: int = 65536
    memory_bytes: int = 268435456
    pids: int = 64
    cpus: float = 1.0
    scratch_bytes: int = 16777216
    output_executable: bool = False

    def tmpfs(self) -> dict[str, str]:
        roots = {'/tmp': f'rw,noexec,nosuid,nodev,size={self.scratch_bytes},mode=1777'}
        if self.output_executable:
            roots['/scratch'] = f'rw,noexec,nosuid,nodev,size={self.scratch_bytes},mode=1777'
            roots['/output'] = f'rw,exec,nosuid,nodev,size={self.scratch_bytes},mode=1777'
        return roots

    def __post_init__(self):
        if type(self.output_executable) is not bool:
            raise SandboxPolicyError('output_executable must be an explicit boolean')
        for name, cap in (("wall_seconds", 60), ("cleanup_seconds", 5), ("cpus", 1)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not 0 < value <= cap:
                raise SandboxPolicyError(f"Invalid {name}")
        for name, cap in (("output_bytes", 1048576), ("memory_bytes", 536870912), ("pids", 128), ("scratch_bytes", 67108864)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= cap:
                raise SandboxPolicyError(f"Invalid {name}")


@dataclass(frozen=True)
class LaunchPlan:
    """Host-authored fixed argv from a future reviewed adapter, never model input.

    This is not a registry entry and does not establish readiness/authorization.
    """
    operation_id: str
    image: str
    argv: tuple[str, ...]

    def __post_init__(self):
        if type(self.operation_id) is not str or not _ID.fullmatch(self.operation_id):
            raise SandboxPolicyError("Invalid reviewed operation ID")
        if type(self.image) is not str or not _IMAGE.fullmatch(self.image):
            raise SandboxPolicyError("Image must be an exact sha256 image ID, not a tag")
        if type(self.argv) is not tuple or not 1 <= len(self.argv) <= 32:
            raise SandboxPolicyError("Reviewed argv must be a bounded immutable tuple")
        if any(type(arg) is not str or len(arg) > 16384 or any(c in arg for c in "\x00\r\n") for arg in self.argv):
            raise SandboxPolicyError("Invalid reviewed argv")
        if not re.fullmatch(r"/(?:[a-zA-Z0-9_.-]+/)*[a-zA-Z0-9_.-]+", self.argv[0]) or ".." in self.argv[0].split("/"):
            raise SandboxPolicyError("Reviewed entrypoint must be an absolute container path")


class DockerVerb(StrEnum):
    VERSION = "version"
    INFO = "info"
    IMAGE_INSPECT = "image_inspect"
    CREATE = "create"
    START = "start"
    REMOVE = "remove"
    INSPECT = "inspect"
    OWNED_LIST = "owned_list"


@dataclass(frozen=True)
class DockerCommand:
    """Typed controller request: no arbitrary Docker flags or argv escape hatch."""
    verb: DockerVerb
    operation: LaunchPlan | None = None
    worker: str | None = None

    def __post_init__(self):
        if type(self.verb) is not DockerVerb:
            raise SandboxPolicyError("Unknown Docker verb")
        needs_operation = self.verb in (DockerVerb.IMAGE_INSPECT, DockerVerb.CREATE)
        needs_worker = self.verb in (DockerVerb.CREATE, DockerVerb.START, DockerVerb.REMOVE, DockerVerb.INSPECT, DockerVerb.OWNED_LIST)
        if needs_operation != (type(self.operation) is LaunchPlan):
            raise SandboxPolicyError("Unexpected or missing reviewed operation")
        if not needs_operation and self.operation is not None:
            raise SandboxPolicyError("Unexpected operation")
        if needs_worker:
            if type(self.worker) is not str or not _WORKER.fullmatch(self.worker):
                raise SandboxPolicyError("Expected opaque controller-owned worker ID")
        elif self.worker is not None:
            raise SandboxPolicyError("Unexpected worker ID")

    def arguments(self, limits: SandboxLimits) -> tuple[str, ...]:
        if self.verb == DockerVerb.VERSION:
            return ("version", "--format", "{{json .Server}}")
        if self.verb == DockerVerb.INFO:
            return ("info", "--format", "{{json .}}")
        if self.verb == DockerVerb.IMAGE_INSPECT:
            return ("image", "inspect", self.operation.image)
        if self.verb == DockerVerb.START:
            return ("start", "--attach", self.worker)
        if self.verb == DockerVerb.INSPECT:
            return ("container", "inspect", self.worker)
        if self.verb == DockerVerb.OWNED_LIST:
            return ("container", "ls", "--all", "--no-trunc", "--filter", f"name=^/{self.worker}$", "--format", "{{.ID}}")
        if self.verb == DockerVerb.REMOVE:
            return ("rm", "--force", "--volumes", self.worker)
        op = self.operation
        return (
            "create", "--pull=never", "--name", self.worker,
            "--label", f"labproof.worker={self.worker}",
            "--network=none", "--ipc=none", "--user=65532:65532", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            f"--memory={limits.memory_bytes}", f"--memory-swap={limits.memory_bytes}",
            f"--cpus={limits.cpus}", f"--pids-limit={limits.pids}",
            "--ulimit=nofile=128:128", "--ulimit=core=0:0", "--restart=no",
            "--log-driver=none", "--init=false", "--workdir=/tmp",
            *(f'--tmpfs={root}:{options}' for root, options in limits.tmpfs().items()),
            "--env=HOME=/tmp", "--env=TMPDIR=/tmp", "--env=LANG=C",
            "--entrypoint", op.argv[0], op.image, *op.argv[1:],
        )


def policy_fingerprint(operation: LaunchPlan, limits: SandboxLimits) -> str:
    """Bind live acceptance to this controller's exact endpoint and rules."""
    return _policy_fingerprint(operation, limits,
                               (DOCKER_EXECUTABLE, DOCKER_ENDPOINT, REVIEWED_ENVIRONMENT))


def reviewed_policy_bindings(operations, limits):
    """Offline-only whole-policy alternatives; never select execution authority."""
    return tuple(tuple(_policy_fingerprint(operation, limits, controller) for operation in operations)
                 for controller in REVIEWED_CONTROLLERS.values())


def _policy_fingerprint(operation, limits, controller):
    executable, endpoint, environment = controller
    limit_data = asdict(limits)
    # Preserve the original all-noexec policy identity for retained runs; enabling
    # the explicitly reviewed Rust extension adds a field and different mounts.
    if not limits.output_executable:
        limit_data.pop('output_executable')
    return sha256(canonical({
        "schema": "sandbox-policy-foundation-1", "executable": executable,
        "endpoint": endpoint, "environment": dict(environment),
        "operation": asdict(operation), "limits": limit_data,
        "create": DockerCommand(DockerVerb.CREATE, operation, "labproof-" + "0" * 32).arguments(limits),
    })).hexdigest()
