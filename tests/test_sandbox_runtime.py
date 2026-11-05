"""Injected processes only. None of these tests establish real containment."""
from dataclasses import replace
import io
from pathlib import Path
import subprocess
import threading
import time

import pytest

from labproof.packs import ExecutionAcceptance, PackError, REGISTRY
from labproof.sandbox import SandboxNotReady, SandboxRuntime
from labproof.sandbox.policy import (
    DOCKER_ENDPOINT, DOCKER_EXECUTABLE, DockerCommand, DockerVerb, LaunchPlan,
    SandboxLimits, SandboxPolicyError, policy_fingerprint,
)
from labproof.sandbox.readiness import ReadinessGate
from labproof.sandbox.supervisor import DockerSupervisor


class FakeProcess:
    def __init__(self, output=b"ok", *, running=False, kill_fails=False):
        self.stdout = io.BytesIO(output)
        self.returncode = None if running else 0
        self.killed = False
        self.kill_fails = kill_fails

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        if self.kill_fails:
            raise OSError("injected kill failure")
        self.returncode = -9

    def wait(self, timeout):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.returncode


def request():
    return {"schema_version": "1.0", "pack_id": "python", "operation_id": "python-ast",
            "fixture_id": "python-synthetic-v1", "parameters": {"variant": "alpha"}}


def test_fixed_executable_local_endpoint_and_environment(monkeypatch):
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
                "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY", "HTTP_PROXY", "PYTHONPATH"):
        monkeypatch.setenv(key, "must-not-leak")
    observed = {}

    def launch(argv, **kwargs):
        observed.update(argv=argv, **kwargs)
        assert Path(kwargs["cwd"]).is_dir()
        assert list(Path(kwargs["env"]["DOCKER_CONFIG"]).iterdir()) == []
        return FakeProcess()

    result = DockerSupervisor(popen=launch).run(DockerCommand(DockerVerb.VERSION))
    assert result.ok and result.output == b"ok"
    assert observed["argv"][0] == DOCKER_EXECUTABLE
    assert observed["argv"][3:5] == ("--host", DOCKER_ENDPOINT)
    assert observed["shell"] is False
    assert observed["stderr"] == subprocess.STDOUT
    assert observed["stdin"] == subprocess.DEVNULL
    assert observed["close_fds"] is True
    assert "must-not-leak" not in observed["env"].values()
    assert not Path(observed["cwd"]).exists()


def test_output_is_streamed_with_combined_hard_cap():
    result = DockerSupervisor(SandboxLimits(output_bytes=100), popen=lambda *a, **k: FakeProcess(b"z" * 1000000)).run(DockerCommand(DockerVerb.INFO))
    assert result.output == b"z" * 100
    assert result.truncated and not result.ok
    assert result.cleanup_ok


def test_output_exhaustion_stops_cli_before_deadline():
    process = FakeProcess(b"z" * 101, running=True)
    result = DockerSupervisor(SandboxLimits(output_bytes=100, wall_seconds=5),
                              popen=lambda *a, **k: process).run(DockerCommand(DockerVerb.INFO))
    assert result.truncated and process.killed and result.cleanup_ok
    assert not result.timed_out
    assert result.output == b"z" * 100


def test_exact_cap_is_not_truncation():
    result = DockerSupervisor(SandboxLimits(output_bytes=100), popen=lambda *a, **k: FakeProcess(b"z" * 100)).run(DockerCommand(DockerVerb.INFO))
    assert result.ok and not result.truncated


def test_silent_process_timeout_kills_cli_with_bounded_wait():
    process = FakeProcess(running=True)
    start = time.monotonic()
    result = DockerSupervisor(SandboxLimits(wall_seconds=.03, cleanup_seconds=.03), popen=lambda *a, **k: process).run(DockerCommand(DockerVerb.INFO))
    assert result.timed_out and process.killed and result.cleanup_ok
    assert time.monotonic() - start < 1


def test_cancellation_during_execution():
    cancelled = threading.Event()
    process = FakeProcess(running=True)

    def launch(*args, **kwargs):
        cancelled.set()
        return process

    result = DockerSupervisor(popen=launch).run(DockerCommand(DockerVerb.INFO), cancel=cancelled)
    assert result.cancelled and process.killed and not result.ok


def test_precancel_and_expired_deadline_do_not_spawn():
    def forbidden(*args, **kwargs):
        raise AssertionError("Must not launch")
    supervisor = DockerSupervisor(popen=forbidden)
    event = threading.Event()
    event.set()
    assert supervisor.run(DockerCommand(DockerVerb.INFO), cancel=event).cancelled
    assert supervisor.run(DockerCommand(DockerVerb.INFO), deadline=0).timed_out


def test_cleanup_failure_poison_supervisor():
    process = FakeProcess(running=True, kill_fails=True)
    supervisor = DockerSupervisor(SandboxLimits(wall_seconds=.01, cleanup_seconds=.01), popen=lambda *a, **k: process)
    result = supervisor.run(DockerCommand(DockerVerb.INFO))
    assert not result.cleanup_ok
    with pytest.raises(SandboxPolicyError, match="cleanup failed"):
        supervisor.run(DockerCommand(DockerVerb.INFO))


def test_missing_executable_is_safe_failure():
    def missing(*args, **kwargs):
        raise FileNotFoundError("missing")
    result = DockerSupervisor(popen=missing).run(DockerCommand(DockerVerb.INFO))
    assert not result.ok and result.returncode is None
    assert result.error == "process_start_or_io_failed:FileNotFoundError"


def test_invalid_supervisor_requests_are_rejected():
    supervisor = DockerSupervisor()
    with pytest.raises(SandboxPolicyError):
        supervisor.run(["docker", "run", "--privileged"])
    with pytest.raises(SandboxPolicyError):
        supervisor.run(DockerCommand(DockerVerb.INFO), deadline=float("nan"))


def test_runtime_is_blocked_and_never_spawns(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No subprocess authorized")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    runtime = SandboxRuntime()
    assert runtime.status().to_dict()["state"] == "blocked"
    status = runtime.status(request(), acceptance=True)
    assert not status.ready and not status.containment_verified
    assert "worker_assertion_is_not_acceptance" in status.reasons
    with pytest.raises(SandboxNotReady):
        runtime.execute(request(), acceptance=True)


@pytest.mark.parametrize("alter", [
    {"operation_id": "python -c evil"}, {"argv": ["/bin/sh"]},
    {"parameters": {"variant": "defective"}}, {"parameters": {"variant": "alpha", "command": "x"}},
    {"fixture_id": "../../fixture"},
])
def test_runtime_uses_shared_registry_and_rejects_model_commands(alter):
    with pytest.raises(PackError):
        SandboxRuntime().execute({**request(), **alter})


def test_forged_matching_acceptance_never_grants_readiness():
    pack = REGISTRY.get("python")
    pack = replace(pack, image_digest="sha256:" + "a" * 64)
    plan = LaunchPlan("python-ast", pack.image_digest, ("/adapter/check",))
    acceptance = ExecutionAcceptance(pack.digest, pack.image_digest, "fake-runtime",
                                     policy_fingerprint(plan, SandboxLimits()), "f" * 64)
    gate = ReadinessGate()
    status = gate.inspect(pack=pack, acceptance=acceptance, runtime_id="fake-runtime", plan=plan)
    assert not status.ready
    assert "canary_evidence_not_independently_authenticated" in status.reasons
    stale = gate.inspect(pack=pack, acceptance=acceptance, runtime_id="changed", plan=plan,
                         limits=SandboxLimits(pids=3))
    assert "runtime_acceptance_mismatch" in stale.reasons
    assert "policy_acceptance_mismatch" in stale.reasons
    stale_image = gate.inspect(pack=replace(pack, image_digest="sha256:" + "b" * 64), acceptance=acceptance)
    assert "pack_or_image_acceptance_mismatch" in stale_image.reasons


def test_open_output_pipe_cannot_defeat_deadline():
    unblock = threading.Event()

    class BlockingPipe:
        def read(self, size):
            unblock.wait(1)
            return b""
        def close(self):
            pass

    process = FakeProcess()
    process.stdout = BlockingPipe()
    supervisor = DockerSupervisor(SandboxLimits(wall_seconds=.01, cleanup_seconds=.01), popen=lambda *a, **k: process)
    try:
        started = time.monotonic()
        result = supervisor.run(DockerCommand(DockerVerb.INFO))
        assert result.timed_out and not result.cleanup_ok
        assert time.monotonic() - started < .5
    finally:
        unblock.set()


from labproof.sandbox.runtime import LiveSandboxSession, LifecycleError
from labproof.sandbox.supervisor import ProcessResult
from labproof.contracts import canonical


class FakeDaemon:
    def __init__(self, limits=SandboxLimits()):
        self.limits = limits
        self.containers = {}
        self.calls = []
        self.identity = 'daemon-one'
        self.mutate = None
        self.fail_remove = False

    def run(self, command, **kwargs):
        self.calls.append(command)
        verb = command.verb
        data = None
        raw = b''
        rc, timeout, truncated = 0, False, False
        if verb == DockerVerb.INFO:
            data = dict(ID=self.identity, OSType='linux', CgroupVersion='2', MemoryLimit=True, SwapLimit=True, PidsLimit=True, CpuCfsQuota=True)
        elif verb == DockerVerb.VERSION:
            data = {'Version': '26'}
        elif verb == DockerVerb.IMAGE_INSPECT:
            data = [{'Id': command.operation.image, 'Config': {'Env': ['PATH=/usr/local/bin:/usr/bin:/bin']}}]
        elif verb == DockerVerb.CREATE:
            self.containers[command.worker] = [command.operation, False]
            raw = b'a' * 64
        elif verb == DockerVerb.START:
            plan = self.containers[command.worker][0]
            self.containers[command.worker][1] = True
            if plan.operation_id == 'canary-policy':
                data = dict(uid=65532,gid=65532,root_write_denied=True,fresh=True,cap_eff='0000000000000000',cap_bnd='0000000000000000',nnp='1',interfaces=['lo'],socket_absent=True,env={'PATH':'/usr/bin'},memory=str(self.limits.memory_bytes),swap='0',pids=str(self.limits.pids),cpu='100000 100000',tmp_type='tmpfs',tmp_options=['noexec','nosuid','nodev'],tmp_bytes=self.limits.scratch_bytes)
                if plan.argv[0] == '/bin/sh':
                    data.pop('env'); data.pop('interfaces'); data.pop('cpu')
                    data.pop('tmp_type'); data.pop('tmp_options')
                    data.update(network_none=True,tmp_noexec=True,env_hex=b'PATH=/usr/bin\x00PWD=/tmp\x00'.hex(),cpu_hex=b'100000 100000'.hex(),tmp_hex=b'tmpfs rw,noexec,nosuid,nodev'.hex())
                    if self.limits.output_executable:
                        data.update(output_fresh=True,output_exec=True,scratch_noexec=True,output_hex=b'tmpfs rw,nosuid,nodev'.hex(),scratch_hex=b'tmpfs rw,noexec,nosuid,nodev'.hex(),output_bytes=self.limits.scratch_bytes,scratch_bytes=self.limits.scratch_bytes)
            elif plan.operation_id == 'canary-timeout':
                timeout = True
                rc = -9
            elif plan.operation_id == 'canary-output':
                raw = b'x' * self.limits.output_bytes
                truncated = True
            else:
                raw = b'fixture output'
        elif verb == DockerVerb.INSPECT:
            plan, stopped = self.containers[command.worker]
            l = self.limits
            row = dict(Id='a'*64,Image=plan.image,Name='/'+command.worker,
                       Config=dict(User='65532:65532',WorkingDir='/tmp',Entrypoint=[plan.argv[0]],Cmd=list(plan.argv[1:]),Labels={'labproof.worker':command.worker},Env=['HOME=/tmp']),
                       HostConfig=dict(NetworkMode='none',IpcMode='none',ReadonlyRootfs=True,Privileged=False,Memory=l.memory_bytes,MemorySwap=l.memory_bytes,NanoCpus=int(l.cpus*1e9),PidsLimit=l.pids,CapDrop=['ALL'],SecurityOpt=['no-new-privileges:true'],RestartPolicy={'Name':'no'},LogConfig={'Type':'none'},Tmpfs=l.tmpfs()),
                       State=dict(Running=False,Status='exited' if stopped else 'created',ExitCode=0),Mounts=[],NetworkSettings={'Networks':{}})
            if self.mutate:
                self.mutate(row)
            data = [row]
        elif verb == DockerVerb.REMOVE:
            if self.fail_remove:
                rc = 1
            else:
                self.containers.pop(command.worker, None)
        elif verb == DockerVerb.OWNED_LIST:
            raw = b'a'*64 if command.worker in self.containers else b''
        else:
            raise AssertionError(verb)
        return ProcessResult(canonical(data) if data is not None else raw,rc,timeout,False,truncated,True,None,.01)


def live_session(daemon=None):
    daemon = daemon or FakeDaemon()
    plan = LaunchPlan('python-ast-alpha', 'sha256:'+'a'*64, ('/usr/local/bin/python','-I','/adapter.py','alpha'))
    return LiveSandboxSession((plan,),language='python',supervisor=daemon), daemon


def test_attach_cli_failure_cannot_grant_acceptance():
    session, daemon = live_session()
    original = daemon.run

    def failed_attach(command, **kwargs):
        result = original(command, **kwargs)
        if command.verb == DockerVerb.START and daemon.containers[command.worker][0].operation_id == 'canary-policy':
            return replace(result, returncode=1)
        return result

    daemon.run = failed_attach
    with pytest.raises(LifecycleError, match='CLI supervision'):
        session.accept()
    assert not daemon.containers
    with pytest.raises(LifecycleError):
        session.execute('python-ast-alpha')


def test_nonzero_worker_exit_keeps_output_and_does_not_poison_session():
    session, daemon = live_session()
    session.accept()
    original = daemon.run

    def exited_worker(command, **kwargs):
        result = original(command, **kwargs)
        if command.verb == DockerVerb.START:
            return replace(result, returncode=7, output=b'worker failed')
        return result

    daemon.run = exited_worker
    daemon.mutate = lambda row: row['State'].update(ExitCode=7)
    result = session.execute('python-ast-alpha')
    assert result.returncode == 7 and result.output == b'worker failed'
    assert not daemon.containers
    assert session.execute('python-ast-alpha').returncode == 7


def test_attach_cli_failure_cannot_be_reported_as_successful_execution():
    session, daemon = live_session()
    session.accept()
    original = daemon.run

    def failed_attach(command, **kwargs):
        result = original(command, **kwargs)
        if command.verb == DockerVerb.START:
            return replace(result, returncode=1)
        return result

    daemon.run = failed_attach
    with pytest.raises(LifecycleError, match='CLI supervision'):
        session.execute('python-ast-alpha')
    assert not daemon.containers


def test_session_acceptance_is_earned_and_not_transferable():
    session, daemon = live_session()
    with pytest.raises(LifecycleError, match='canaries'):
        session.execute('python-ast-alpha')
    report = session.accept()
    assert report['timeout_cleanup'] and report['output_bounded']
    canonical(report)
    assert len(report['canaries']) == 2
    result = session.execute('python-ast-alpha')
    assert result.output == b'fixture output' and result.returncode == 0
    assert result.execution_id == result.reset_id == result.container_id
    assert result.cleanup_ok and not daemon.containers
    other, _ = live_session()
    with pytest.raises(LifecycleError):
        other.execute('python-ast-alpha')
    with pytest.raises(TypeError):
        other.execute('python-ast-alpha', acceptance=report)


@pytest.mark.parametrize('mutation', [
    lambda r:r['HostConfig'].update(Privileged=True),
    lambda r:r['HostConfig'].update(NetworkMode='host'),
    lambda r:r['HostConfig'].update(Binds=['/secret:/secret']),
    lambda r:r['HostConfig'].update(CapAdd=['SYS_ADMIN']),
    lambda r:r['Config'].update(User='0'),
    lambda r:r['Config'].update(Env=['API_KEY=secret']),
    lambda r:r.update(Image='sha256:'+'b'*64),
    lambda r:r.update(Mounts=[{'Type':'bind','Destination':'/tmp'}]),
])
def test_actual_policy_inspection_prevents_start_and_cleans(mutation):
    session, daemon = live_session()
    daemon.mutate = mutation
    with pytest.raises(LifecycleError):
        session.accept()
    assert not any(c.verb == DockerVerb.START for c in daemon.calls)
    assert any(c.verb == DockerVerb.REMOVE for c in daemon.calls)
    assert not daemon.containers


def test_cleanup_failure_permanently_poisons_session():
    session, daemon = live_session()
    daemon.fail_remove = True
    with pytest.raises(LifecycleError, match='removal'):
        session.accept()
    daemon.fail_remove = False
    with pytest.raises(LifecycleError, match='poisoned'):
        session.accept()


def test_daemon_change_revokes_acceptance_before_fixture():
    session, daemon = live_session()
    session.accept()
    daemon.identity = 'new-daemon'
    before = len(daemon.calls)
    with pytest.raises(LifecycleError, match='Stale'):
        session.execute('python-ast-alpha')
    assert not any(c.verb == DockerVerb.CREATE for c in daemon.calls[before:])


def test_keyboard_interrupt_still_removes_owned_worker():
    session, daemon = live_session()
    original = daemon.run
    def interrupted(command, **kwargs):
        if command.verb == DockerVerb.START:
            raise KeyboardInterrupt()
        return original(command, **kwargs)
    daemon.run = interrupted
    with pytest.raises(KeyboardInterrupt):
        session.accept()
    assert not daemon.containers
    assert daemon.calls[-2].verb == DockerVerb.REMOVE
    assert daemon.calls[-1].verb == DockerVerb.OWNED_LIST
    assert session._accepted is None


def test_truncated_attach_skips_stopped_inspection_and_removes():
    session, daemon = live_session()
    original = daemon.run
    def running_after_truncation(command, **kwargs):
        result = original(command, **kwargs)
        if command.verb == DockerVerb.START and result.truncated:
            # Docker attach is killed; worker may still be running. A stopped
            # inspection here would reject and break output canary acceptance.
            daemon.containers[command.worker][1] = False
        return result
    daemon.run = running_after_truncation
    assert session.accept()['output_bounded']
    assert not daemon.containers


def test_reviewed_python_bytecode_environment_is_exact():
    LiveSandboxSession._validate_env(['PYTHONDONTWRITEBYTECODE=1'])
    for value in ('0', '', 'yes'):
        with pytest.raises(LifecycleError):
            LiveSandboxSession._validate_env(['PYTHONDONTWRITEBYTECODE='+value])


def test_public_gpg_keys_metadata_is_bounded_and_hex_only():
    key = '0123456789ABCDEF' * 2 + '01234567'
    for value in (key, ' '+key+'  '+key.lower()+' ', ' '.join([key]*32), key+' \t'+key, '\t'+key+'\t'):
        LiveSandboxSession._validate_env(['GPG_KEYS='+value])
    for value in ('', ' ', '\t', key[:-1], key+'0', key+'\n', key+'\r'+key, key+'\v'+key, key+' '+key,
                  'G'*40, ' '.join([key]*33), ' '*2049+key):
        with pytest.raises(LifecycleError, match='GPG_KEYS'):
            LiveSandboxSession._validate_env(['GPG_KEYS='+value])
    with pytest.raises(LifecycleError, match='Duplicate'):
        LiveSandboxSession._validate_env(['GPG_KEYS='+key, 'GPG_KEYS='+key])
    with pytest.raises(LifecycleError, match='Unreviewed'):
        LiveSandboxSession._validate_env(['GPG_KEYS='+key, 'UNKNOWN_KEY=secret'])


def test_rust_executable_output_requires_explicit_scoped_policy():
    plan = LaunchPlan('fixed','sha256:'+'a'*64,('/worker/observe',))
    for language in ('python','node','c'):
        with pytest.raises(SandboxPolicyError, match='Rust only'):
            LiveSandboxSession((plan,),language=language,limits=SandboxLimits(output_executable=True))
    with pytest.raises(SandboxPolicyError, match='explicitly'):
        LiveSandboxSession((plan,),language='rust')


@pytest.mark.parametrize('language', ['c','rust'])
def test_native_canary_report_normalization_and_cleanup(language):
    limits = SandboxLimits(output_executable=language=='rust')
    daemon = FakeDaemon(limits)
    plan = LaunchPlan('fixed','sha256:'+'a'*64,('/worker/observe','alpha'))
    session = LiveSandboxSession((plan,),language=language,limits=limits,supervisor=daemon)
    report = session.accept()
    data = report['canaries'][0]['observations']
    assert data['env'] == {'PATH':'/usr/bin','PWD':'/tmp'}
    assert data['cpu'] == '100000 100000' and data['interfaces'] == ['lo']
    assert data['tmp_noexec'] and data['tmp_type'] == 'tmpfs'
    assert not any(k.endswith('_hex') for k in data)
    if language == 'rust':
        assert data['output_exec'] and data['scratch_noexec']
        assert 'noexec' not in data['output_options']
        assert 'noexec' in data['scratch_options']
    assert session.execute('fixed').cleanup_ok
    assert not daemon.containers


def test_native_canary_scripts_only_use_reviewed_fixed_tools():
    for language in ('c','rust'):
        session = LiveSandboxSession((LaunchPlan('fixed','sha256:'+'a'*64,('/worker/observe',)),),language=language,limits=SandboxLimits(output_executable=language=='rust'))
        for kind in ('policy','timeout','output'):
            plan = session._canary_plan(kind)
            assert plan.argv[:2] == ('/bin/sh','-c')
            assert '\n' not in plan.argv[2] and len(plan.argv[2]) < 16384
        policy = session._canary_plan('policy').argv[2]
        assert '/usr/bin/cp /usr/bin/true /tmp/' in policy
        assert ('/output/labproof-exec-canary' in policy) == (language == 'rust')


def test_canary_scripts_are_fixed_bounded_launch_plans():
    for language in ('python', 'node'):
        session = LiveSandboxSession((LaunchPlan('fixed','sha256:'+'a'*64,('/adapter',)),),language=language)
        for kind in ('policy','timeout','output'):
            plan = session._canary_plan(kind)
            assert plan.operation_id == 'canary-' + kind
            assert plan.argv[0] == '/usr/local/bin/' + ('python' if language == 'python' else 'node')
