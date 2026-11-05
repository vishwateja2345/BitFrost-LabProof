from dataclasses import replace

import pytest

from labproof.sandbox.policy import (
    DOCKER_ENDPOINT, DOCKER_EXECUTABLE, REVIEWED_ENVIRONMENT,
    DockerCommand, DockerVerb, LaunchPlan, SandboxLimits,
    SandboxPolicyError, policy_fingerprint,
)

IMAGE = "sha256:" + "a" * 64
WORKER = "labproof-" + "b" * 32
PLAN = LaunchPlan("python-ast", IMAGE, ("/usr/bin/python3", "-I", "/adapter/check.py"))


@pytest.mark.parametrize("name,value", [
    ("wall_seconds", True), ("wall_seconds", float("nan")),
    ("wall_seconds", float("inf")), pytest.param("wall_seconds", 10 ** 10000, id="huge-int"),
    ("cleanup_seconds", 0), ("cpus", 2), ("memory_bytes", -1),
    ("pids", 129), ("output_bytes", 1.5), ("output_bytes", True),
    ("scratch_bytes", 67108865),
])
def test_limits_fail_closed(name, value):
    with pytest.raises(SandboxPolicyError):
        SandboxLimits(**{name: value})


@pytest.mark.parametrize("image", ["python:latest", "python", "--privileged", "sha256:" + "A" * 64, "sha256:" + "a" * 63])
def test_image_requires_exact_local_digest(image):
    with pytest.raises(SandboxPolicyError):
        replace(PLAN, image=image)


@pytest.mark.parametrize("argv", [["/bin/tool"], (), ("tool",), ("/bin/../tool",), ("/bin/tool", "\x00")])
def test_launch_plan_requires_fixed_absolute_argv(argv):
    with pytest.raises(SandboxPolicyError):
        replace(PLAN, argv=argv)


def test_policy_has_fixed_containment_flags_and_no_mounts():
    args = DockerCommand(DockerVerb.CREATE, PLAN, WORKER).arguments(SandboxLimits())
    required = {"--pull=never", "--network=none", "--ipc=none", "--user=65532:65532",
                "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
                "--memory=268435456", "--memory-swap=268435456", "--pids-limit=64",
                "--restart=no", "--log-driver=none", "--ulimit=core=0:0"}
    assert required <= set(args)
    assert not any(a.startswith(("--mount", "--volume", "--privileged", "--publish", "--device")) for a in args)
    assert "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16777216,mode=1777" in args
    assert args[-3:] == (IMAGE, "-I", "/adapter/check.py")
    assert "DOCKER_HOST" not in REVIEWED_ENVIRONMENT
    assert "DOCKER_CONTEXT" not in REVIEWED_ENVIRONMENT
    assert DOCKER_EXECUTABLE.startswith(("C:\\", "/"))
    assert DOCKER_ENDPOINT in ("npipe:////./pipe/docker_engine", "unix:///var/run/docker.sock")


@pytest.mark.parametrize("command", [
    lambda: DockerCommand("start", worker=WORKER),
    lambda: DockerCommand(DockerVerb.START, worker="other-container"),
    lambda: DockerCommand(DockerVerb.REMOVE, worker="--all"),
    lambda: DockerCommand(DockerVerb.CREATE, PLAN),
    lambda: DockerCommand(DockerVerb.VERSION, PLAN),
    lambda: DockerCommand(DockerVerb.INFO, worker=WORKER),
    lambda: DockerCommand(DockerVerb.IMAGE_INSPECT),
])
def test_no_arbitrary_command_or_worker_names(command):
    with pytest.raises(SandboxPolicyError):
        command()


def test_fingerprint_binds_plan_and_limits():
    original = policy_fingerprint(PLAN, SandboxLimits())
    assert len(original) == 64
    assert original == policy_fingerprint(PLAN, SandboxLimits())
    assert original != policy_fingerprint(replace(PLAN, image="sha256:" + "c" * 64), SandboxLimits())
    assert original != policy_fingerprint(PLAN, SandboxLimits(output_bytes=100))
    assert original != policy_fingerprint(replace(PLAN, argv=("/other/tool",)), SandboxLimits())


def test_rust_output_policy_is_bounded_and_distinct():
    limits = SandboxLimits(output_executable=True)
    assert limits.tmpfs() == {
        '/tmp': 'rw,noexec,nosuid,nodev,size=16777216,mode=1777',
        '/scratch': 'rw,noexec,nosuid,nodev,size=16777216,mode=1777',
        '/output': 'rw,exec,nosuid,nodev,size=16777216,mode=1777',
    }
    assert policy_fingerprint(PLAN, limits) != policy_fingerprint(PLAN, SandboxLimits())
    with pytest.raises(SandboxPolicyError):
        SandboxLimits(output_executable=1)


def test_original_noexec_policy_digest_remains_compatible():
    from dataclasses import asdict
    from hashlib import sha256
    from labproof.contracts import canonical
    limits = SandboxLimits()
    old_limits = asdict(limits)
    old_limits.pop('output_executable')
    original = sha256(canonical({
        'schema':'sandbox-policy-foundation-1','executable':DOCKER_EXECUTABLE,
        'endpoint':DOCKER_ENDPOINT,'environment':dict(REVIEWED_ENVIRONMENT),
        'operation':asdict(PLAN),'limits':old_limits,
        'create':DockerCommand(DockerVerb.CREATE,PLAN,'labproof-'+'0'*32).arguments(limits),
    })).hexdigest()
    assert policy_fingerprint(PLAN,limits) == original


def test_all_controller_verbs_are_fixed():
    limits = SandboxLimits()
    assert DockerCommand(DockerVerb.START, worker=WORKER).arguments(limits) == ("start", "--attach", WORKER)
    assert DockerCommand(DockerVerb.REMOVE, worker=WORKER).arguments(limits) == ("rm", "--force", "--volumes", WORKER)
    assert DockerCommand(DockerVerb.IMAGE_INSPECT, PLAN).arguments(limits) == ("image", "inspect", IMAGE)
