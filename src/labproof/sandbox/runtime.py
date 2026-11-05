"""Trusted local Docker lifecycle; legacy registry API remains fail closed."""
from dataclasses import dataclass
from hashlib import sha256
import threading
import time
from types import MappingProxyType
import uuid

from ..contracts import canonical, parse_json
from ..packs import REGISTRY, OperationRequest, PackError
from .policy import DockerCommand, DockerVerb, LaunchPlan, SandboxLimits, SandboxPolicyError, policy_fingerprint
from .readiness import ReadinessGate, ReadinessStatus
from .supervisor import DockerSupervisor


class SandboxNotReady(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__('Sandbox blocked: ' + ', '.join(status.reasons))


class SandboxRuntime:
    """Legacy model boundary. No imported acceptance object enables this API."""
    def status(self, request=None, *, acceptance=None):
        if request is None:
            return ReadinessGate().inspect(acceptance=acceptance)
        validated = REGISTRY.validate_operation(request)
        status = ReadinessGate().inspect(pack=REGISTRY.get(validated.pack_id), acceptance=acceptance)
        try:
            REGISTRY.require_execution(validated, acceptance)
        except PackError as exc:
            return ReadinessStatus('blocked', (*status.reasons, str(exc)))
        return status

    def execute(self, request, *, acceptance=None):
        raise SandboxNotReady(self.status(request, acceptance=acceptance))


class LifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerResult:
    execution_id: str
    container_id: str
    reset_id: str
    image_id: str
    policy_digest: str
    runtime_id: str
    output: bytes
    returncode: int | None
    timed_out: bool
    cancelled: bool
    truncated: bool
    cleanup_ok: bool
    elapsed_seconds: float


# Fixed trusted canary programs, not fixture or model text. Unsupported cgroup
# layouts fail closed. Network testing inspects only the worker's own interfaces.
_PY_CANARY = '''import os,json
from pathlib import Path
status=dict(x.split(':',1) for x in Path('/proc/self/status').read_text().splitlines() if ':' in x)
blocked=False
try:
 p=os.open('/labproof-write-canary',os.O_CREAT|os.O_WRONLY,0o600);os.close(p)
except OSError:
 blocked=True
scratch=Path('/tmp/labproof-fresh-canary')
fresh=not scratch.exists()
scratch.write_text('owned')
mount=[x for x in Path('/proc/mounts').read_text().splitlines() if x.split()[1]=='/tmp'][0].split()
cg=Path('/sys/fs/cgroup')
print(json.dumps(dict(uid=os.getuid(),gid=os.getgid(),root_write_denied=blocked,fresh=fresh,cap_eff=status['CapEff'].strip(),cap_bnd=status['CapBnd'].strip(),nnp=status['NoNewPrivs'].strip(),interfaces=sorted(os.listdir('/sys/class/net')),socket_absent=not any(Path(p).exists() for p in ['/var/run/docker.sock','/run/docker.sock','/run/containerd/containerd.sock']),env=dict(os.environ),memory=(cg/'memory.max').read_text().strip(),swap=(cg/'memory.swap.max').read_text().strip(),pids=(cg/'pids.max').read_text().strip(),cpu=(cg/'cpu.max').read_text().strip(),tmp_type=mount[2],tmp_options=mount[3].split(','),tmp_bytes=os.statvfs('/tmp').f_blocks*os.statvfs('/tmp').f_frsize)))
'''
_NODE_CANARY = """const fs=require('fs'),p='/tmp/labproof-fresh-canary';let denied=false;try{fs.writeFileSync('/labproof-write-canary','x')}catch(e){denied=true}const fresh=!fs.existsSync(p);fs.writeFileSync(p,'owned');const status=Object.fromEntries(fs.readFileSync('/proc/self/status','utf8').trim().split('\\n').map(x=>{const i=x.indexOf(':');return [x.slice(0,i),x.slice(i+1).trim()]}));const m=fs.readFileSync('/proc/mounts','utf8').split('\\n').map(x=>x.split(' ')).find(x=>x[1]==='/tmp'),s=fs.statfsSync('/tmp');const read=x=>fs.readFileSync('/sys/fs/cgroup/'+x,'utf8').trim();console.log(JSON.stringify({uid:process.getuid(),gid:process.getgid(),root_write_denied:denied,fresh,cap_eff:status.CapEff,cap_bnd:status.CapBnd,nnp:status.NoNewPrivs,interfaces:fs.readdirSync('/sys/class/net').sort(),socket_absent:!['/var/run/docker.sock','/run/docker.sock','/run/containerd/containerd.sock'].some(x=>fs.existsSync(x)),env:process.env,memory:read('memory.max'),swap:read('memory.swap.max'),pids:read('pids.max'),cpu:read('cpu.max'),tmp_type:m[2],tmp_options:m[3].split(','),tmp_bytes:s.blocks*s.bsize}));"""


# Native compiled-pack canary uses only declared shell/coreutils prerequisites.
# All values containing arbitrary bytes are hex encoded, never interpolated JSON.
_NATIVE_CANARY = r'''
set -eu;
hex() { /usr/bin/od -An -v -tx1 | /usr/bin/tr -d ' \n'; };
root=true; if (printf x > /labproof-write-canary) 2>/dev/null; then root=false; fi;
fresh=true; if test -e /tmp/labproof-fresh-canary; then fresh=false; fi;
printf owned > /tmp/labproof-fresh-canary;
cap=$(/usr/bin/awk '/^CapEff:/{print $2}' /proc/self/status);
bnd=$(/usr/bin/awk '/^CapBnd:/{print $2}' /proc/self/status);
nnp=$(/usr/bin/awk '/^NoNewPrivs:/{print $2}' /proc/self/status);
network=true; for p in /sys/class/net/*; do if test "$p" != /sys/class/net/lo; then network=false; fi; done;
sock=true; for p in /var/run/docker.sock /run/docker.sock /run/containerd/containerd.sock; do if test -e "$p"; then sock=false; fi; done;
/usr/bin/cp /usr/bin/true /tmp/labproof-exec-canary; /usr/bin/chmod 700 /tmp/labproof-exec-canary;
tmp_noexec=true; if /tmp/labproof-exec-canary 2>/dev/null; then tmp_noexec=false; fi;
envhex=$(/usr/bin/env -0 | hex);
cpuhex=$(/usr/bin/cat /sys/fs/cgroup/cpu.max | hex);
tmphex=$(/usr/bin/awk '$2=="/tmp"{print $3 " " $4}' /proc/mounts | hex);
tmpbytes=$(/usr/bin/stat -f -c '%b %S' /tmp | /usr/bin/awk '{printf "%.0f",$1*$2}');
printf '{"uid":%s,"gid":%s,"root_write_denied":%s,"fresh":%s,"cap_eff":"%s","cap_bnd":"%s","nnp":"%s","network_none":%s,"socket_absent":%s,"tmp_noexec":%s,"env_hex":"%s","memory":"%s","swap":"%s","pids":"%s","cpu_hex":"%s","tmp_hex":"%s","tmp_bytes":%s'
"$(/usr/bin/id -u)" "$(/usr/bin/id -g)" "$root" "$fresh" "$cap" "$bnd" "$nnp" "$network" "$sock" "$tmp_noexec" "$envhex" "$(/usr/bin/cat /sys/fs/cgroup/memory.max)" "$(/usr/bin/cat /sys/fs/cgroup/memory.swap.max)" "$(/usr/bin/cat /sys/fs/cgroup/pids.max)" "$cpuhex" "$tmphex" "$tmpbytes";
'''
_NATIVE_RUST = r'''
outputfresh=true; if test -e /output/labproof-exec-canary; then outputfresh=false; fi;
/usr/bin/cp /usr/bin/true /output/labproof-exec-canary; /usr/bin/chmod 700 /output/labproof-exec-canary;
outputexec=false; if /output/labproof-exec-canary; then outputexec=true; fi;
/usr/bin/cp /usr/bin/true /scratch/labproof-exec-canary; /usr/bin/chmod 700 /scratch/labproof-exec-canary;
scratchnoexec=true; if /scratch/labproof-exec-canary 2>/dev/null; then scratchnoexec=false; fi;
outputhex=$(/usr/bin/awk '$2=="/output"{print $3 " " $4}' /proc/mounts | hex);
scratchhex=$(/usr/bin/awk '$2=="/scratch"{print $3 " " $4}' /proc/mounts | hex);
outputbytes=$(/usr/bin/stat -f -c '%b %S' /output | /usr/bin/awk '{printf "%.0f",$1*$2}');
scratchbytes=$(/usr/bin/stat -f -c '%b %S' /scratch | /usr/bin/awk '{printf "%.0f",$1*$2}');
printf ',"output_fresh":%s,"output_exec":%s,"scratch_noexec":%s,"output_hex":"%s","scratch_hex":"%s","output_bytes":%s,"scratch_bytes":%s' "$outputfresh" "$outputexec" "$scratchnoexec" "$outputhex" "$scratchhex" "$outputbytes" "$scratchbytes";
'''


class LiveSandboxSession:
    """Host-only API: plans must come from reviewed provisioning, never a model.

    Acceptance is earned internally by fixed canaries; cannot be deserialized or
    passed as a bool/token. Results evidence tested controls, not escape immunity.
    """
    def __init__(self, plans: tuple[LaunchPlan, ...], *, language: str,
                 limits: SandboxLimits = SandboxLimits(), supervisor=None):
        if type(plans) is not tuple or not plans or any(type(p) is not LaunchPlan for p in plans):
            raise SandboxPolicyError('Expected trusted immutable launch plans')
        if len({p.operation_id for p in plans}) != len(plans) or len({p.image for p in plans}) != 1:
            raise SandboxPolicyError('Session requires unique operations and one image')
        if language not in ('python', 'node', 'c', 'rust') or type(limits) is not SandboxLimits:
            raise SandboxPolicyError('Unsupported language/limits')
        if limits.output_executable and language != 'rust':
            raise SandboxPolicyError('Executable output is reviewed for Rust only')
        if language == 'rust' and not limits.output_executable:
            raise SandboxPolicyError('Rust requires explicitly reviewed executable output policy')
        self._plans = MappingProxyType({p.operation_id: p for p in plans})
        self._image = plans[0].image
        self._language, self._limits = language, limits
        self._supervisor = supervisor or DockerSupervisor(limits)
        # Cleanup must remain available if an attach reader poisoned its runner.
        self._cleanup_supervisor = supervisor or DockerSupervisor(limits)
        self._accepted = None
        self._poisoned = False
        self._lock = threading.Lock()

    def _command(self, command, deadline, cancel=None):
        return self._supervisor.run(command, deadline=deadline, cancel=cancel)

    def _json(self, command, deadline):
        result = self._command(command, deadline)
        if not result.ok:
            raise LifecycleError('Docker metadata failed or exceeded bounds')
        try:
            return parse_json(result.output)
        except ValueError as exc:
            raise LifecycleError('Malformed Docker metadata') from exc

    def _identity(self, deadline):
        info = self._json(DockerCommand(DockerVerb.INFO), deadline)
        version = self._json(DockerCommand(DockerVerb.VERSION), deadline)
        if not isinstance(info, dict) or not isinstance(version, dict) or not info.get('ID') or info.get('OSType') != 'linux':
            raise LifecycleError('Expected identified local Linux daemon')
        if info.get('CgroupVersion') != '2' or any(info.get(x) is not True for x in ('MemoryLimit', 'SwapLimit', 'PidsLimit', 'CpuCfsQuota')):
            raise LifecycleError('Required kernel resource controllers unavailable')
        return sha256(canonical({'id': info['ID'], 'version': version, 'kernel': info.get('KernelVersion'), 'driver': info.get('Driver'), 'security': info.get('SecurityOptions'), 'cgroup': info.get('CgroupDriver')})).hexdigest()

    def _inspect_image(self, plan, deadline):
        rows = self._json(DockerCommand(DockerVerb.IMAGE_INSPECT, plan), deadline)
        if type(rows) is not list or len(rows) != 1 or rows[0].get('Id') != self._image:
            raise LifecycleError('Image identity mismatch')
        config = rows[0].get('Config', {})
        if config.get('Volumes') or config.get('OnBuild') or config.get('Healthcheck'):
            raise LifecycleError('Image has unreviewed volumes/hooks/healthcheck')
        self._validate_env(config.get('Env') or [])

    @staticmethod
    def _validate_env(env):
        allowed = {'PATH', 'HOSTNAME', 'HOME', 'TMPDIR', 'LANG', 'LC_CTYPE', 'PYTHON_VERSION',
                   'PYTHON_SHA256', 'PYTHON_PIP_VERSION', 'PYTHON_GET_PIP_URL',
                   'PYTHON_GET_PIP_SHA256', 'GPG_KEY', 'NODE_VERSION', 'YARN_VERSION',
                   'PYTHONDONTWRITEBYTECODE', 'GCC_VERSION', 'GCC_KEYS', 'GPG_KEYS', 'GCC_MIRRORS',
                   'RUST_VERSION', 'RUSTUP_HOME', 'CARGO_HOME', 'CARGO_NET_OFFLINE', 'PWD'}
        if type(env) is not list or any(type(x) is not str or '=' not in x or x.split('=',1)[0] not in allowed for x in env):
            raise LifecycleError('Unreviewed image/container environment')
        names = [x.split('=',1)[0] for x in env]
        for entry in env:
            name, value = entry.split('=', 1)
            if name == 'GPG_KEYS':
                # Official GCC image metadata, not key material or authority.
                # Official image Dockerfile retains horizontal tabs as well as
                # spaces. Other whitespace/control characters remain forbidden.
                fingerprints = [part for part in value.replace('\t', ' ').split(' ') if part]
                if (len(value) > 2048 or not 1 <= len(fingerprints) <= 32
                        or any(len(part) != 40 or any(c not in '0123456789ABCDEFabcdef' for c in part)
                               for part in fingerprints)):
                    raise LifecycleError('Invalid public GPG_KEYS fingerprints')
        if any(x.startswith('PYTHONDONTWRITEBYTECODE=') and x != 'PYTHONDONTWRITEBYTECODE=1' for x in env):
            raise LifecycleError('Unreviewed Python bytecode environment value')
        exact = {'CARGO_NET_OFFLINE': 'true', 'CARGO_HOME': '/usr/local/cargo',
                 'RUSTUP_HOME': '/usr/local/rustup', 'PWD': '/tmp'}
        if any(k in exact and v != exact[k] for k, v in (x.split('=',1) for x in env)):
            raise LifecycleError('Unreviewed compiled-pack environment value')
        if len(names) != len(set(names)):
            raise LifecycleError('Duplicate environment variable')

    def _inspect_worker(self, plan, worker, deadline, *, stopped=False):
        rows = self._json(DockerCommand(DockerVerb.INSPECT, worker=worker), deadline)
        if type(rows) is not list or len(rows) != 1:
            raise LifecycleError('Invalid container inspection')
        row = rows[0]
        host, config, state = row.get('HostConfig', {}), row.get('Config', {}), row.get('State', {})
        limits = self._limits
        expected = {'NetworkMode': 'none', 'IpcMode': 'none', 'ReadonlyRootfs': True,
                    'Privileged': False, 'Memory': limits.memory_bytes, 'MemorySwap': limits.memory_bytes,
                    'NanoCpus': int(limits.cpus * 1_000_000_000), 'PidsLimit': limits.pids}
        if row.get('Image') != plan.image or row.get('Name') != '/' + worker or any(host.get(k) != v for k,v in expected.items()):
            raise LifecycleError('Actual worker policy/image mismatch')
        if config.get('User') != '65532:65532' or config.get('WorkingDir') != '/tmp' or config.get('Entrypoint') != [plan.argv[0]] or (config.get('Cmd') or []) != list(plan.argv[1:]):
            raise LifecycleError('Actual worker identity/command mismatch')
        if config.get('Labels', {}).get('labproof.worker') != worker or config.get('Volumes') or config.get('Healthcheck'):
            raise LifecycleError('Worker ownership or implicit image behavior mismatch')
        self._validate_env(config.get('Env') or [])
        if set(host.get('CapDrop') or []) != {'ALL'} or host.get('CapAdd') or set(host.get('SecurityOpt') or []) != {'no-new-privileges:true'}:
            raise LifecycleError('Capability/security policy mismatch')
        for key in ('Binds','Mounts','Devices','DeviceRequests','VolumesFrom','Links','PortBindings','ExtraHosts','Dns','GroupAdd'):
            if host.get(key):
                raise LifecycleError('Unexpected host authority: ' + key)
        if any(host.get(k) not in ('', None) for k in ('PidMode', 'UTSMode', 'UsernsMode')):
            raise LifecycleError('Unexpected host namespace')
        if host.get('RestartPolicy', {}).get('Name') != 'no' or host.get('LogConfig', {}).get('Type') != 'none':
            raise LifecycleError('Unexpected restart/log policy')
        if host.get('Tmpfs') != limits.tmpfs():
            raise LifecycleError('Scratch policy mismatch')
        if any(m.get('Type') != 'tmpfs' or m.get('Destination') not in limits.tmpfs() for m in row.get('Mounts', [])):
            raise LifecycleError('Unexpected actual mount')
        networks = row.get('NetworkSettings', {}).get('Networks', {})
        if set(networks) - {'none'} or any(v.get('IPAddress') or v.get('GlobalIPv6Address') for v in networks.values()):
            raise LifecycleError('Unexpected actual network')
        if state.get('Running') or state.get('Paused') or state.get('Restarting'):
            raise LifecycleError('Unexpected running worker during inspection')
        if state.get('Status') != ('exited' if stopped else 'created'):
            raise LifecycleError('Worker lifecycle state mismatch')
        container_id = row.get('Id')
        if not isinstance(container_id, str) or len(container_id) != 64 or any(c not in '0123456789abcdef' for c in container_id):
            raise LifecycleError('Invalid container identity')
        return container_id, state.get('ExitCode') if stopped else None

    def _lifecycle(self, plan, *, runtime_id, cancel=None, wall=None):
        if self._poisoned:
            raise LifecycleError('Session poisoned by cleanup failure')
        started = time.monotonic()
        deadline = started + (self._limits.wall_seconds if wall is None else wall)
        worker = 'labproof-' + uuid.uuid4().hex
        process = None
        exit_code = None
        attempted = False
        try:
            self._inspect_image(plan, deadline)
            attempted = True  # create may succeed on daemon even if CLI fails.
            created = self._command(DockerCommand(DockerVerb.CREATE, plan, worker), deadline, cancel)
            if not created.ok:
                raise LifecycleError('Container creation failed')
            container_id, _ = self._inspect_worker(plan, worker, deadline)
            process = self._command(DockerCommand(DockerVerb.START, worker=worker), deadline, cancel)
            if (process.returncode is not None and not process.timed_out and not process.cancelled
                    and not process.truncated and process.error is None and process.cleanup_ok):
                actual_id, exit_code = self._inspect_worker(plan, worker, deadline, stopped=True)
                if actual_id != container_id:
                    raise LifecycleError('Container replaced during execution')
                if type(exit_code) is not int or exit_code < 0 or process.returncode != exit_code:
                    raise LifecycleError('CLI supervision failed: exit does not match the stopped worker')
        finally:
            if attempted:
                # Cleanup gets one separate reserved budget, independent of
                # cancellation and of how early the worker failed.
                cleanup_deadline = time.monotonic() + self._limits.cleanup_seconds
                try:
                    removed = self._cleanup_supervisor.run(DockerCommand(DockerVerb.REMOVE, worker=worker), deadline=cleanup_deadline)
                    absent = self._cleanup_supervisor.run(DockerCommand(DockerVerb.OWNED_LIST, worker=worker), deadline=cleanup_deadline)
                    if not removed.ok or not absent.ok or absent.output.strip():
                        raise LifecycleError('Owned removal/absence not confirmed')
                except BaseException:
                    self._poisoned = True
                    self._accepted = None
                    raise
        if ((not (process.timed_out or process.cancelled or process.truncated)
             and (exit_code is None or process.returncode != exit_code))
                or process.error is not None or not process.cleanup_ok):
            self._poisoned = True
            raise LifecycleError('CLI supervision failed despite container cleanup')
        return WorkerResult(container_id, container_id, container_id, plan.image,
                            policy_fingerprint(plan, self._limits), runtime_id,
                            process.output, exit_code, process.timed_out, process.cancelled,
                            process.truncated, True, time.monotonic()-started)

    def _canary_plan(self, kind):
        if self._language in ('c', 'rust'):
            policy = _NATIVE_CANARY + (_NATIVE_RUST if self._limits.output_executable else '') + "printf '}';"
            scripts = {'policy': policy.replace('\n', ' '),
                       'timeout': '/usr/bin/sleep 120 & /usr/bin/sleep 120 & wait',
                       'output': '/usr/bin/head -c ' + str(self._limits.output_bytes * 2) + ' /dev/zero'}
            return LaunchPlan('canary-' + kind, self._image, ('/bin/sh', '-c', scripts[kind]))
        if self._language == 'python':
            scripts = {'policy': 'exec(' + repr(_PY_CANARY) + ')',
                       'timeout': "import subprocess,time;subprocess.Popen(['/usr/local/bin/python','-c','import time;time.sleep(120)']);time.sleep(120)",
                       'output': "import os;os.write(1,b'x'*" + str(self._limits.output_bytes * 2) + ")"}
            argv = ('/usr/local/bin/python', '-I', '-c', scripts[kind])
        else:
            scripts = {'policy': _NODE_CANARY,
                       'timeout': "require('child_process').spawn('/usr/local/bin/node',['-e','setTimeout(()=>{},120000)']);setTimeout(()=>{},120000)",
                       'output': "process.stdout.write('x'.repeat(" + str(self._limits.output_bytes * 2) + "))"}
            argv = ('/usr/local/bin/node', '-e', scripts[kind])
        return LaunchPlan('canary-' + kind, self._image, argv)

    def _check_canary(self, result):
        if result.timed_out or result.cancelled or result.truncated or result.returncode != 0:
            raise LifecycleError('Policy canary failed')
        data = parse_json(result.output)
        if self._language in ('c', 'rust'):
            if data.get('network_none') is not True or data.get('tmp_noexec') is not True:
                raise LifecycleError('Native network/noexec canary failed')
            try:
                env = bytes.fromhex(data.pop('env_hex')).decode('utf-8').rstrip('\x00').split('\x00')
                self._validate_env(env)
                data['env'] = dict(item.split('=', 1) for item in env)
                data['interfaces'] = ['lo']
                data['cpu'] = bytes.fromhex(data.pop('cpu_hex')).decode('ascii').strip()
                for root in ('tmp', 'output', 'scratch') if self._limits.output_executable else ('tmp',):
                    mount = bytes.fromhex(data.pop(root+'_hex')).decode('ascii').split()
                    if len(mount) != 2:
                        raise LifecycleError('Native mount observation invalid')
                    data[root+'_type'], options = mount
                    data[root+'_options'] = options.split(',')
                    required = {'nosuid', 'nodev'} | ({'noexec'} if root != 'output' else set())
                    if mount[0] != 'tmpfs' or not required <= set(data[root+'_options']):
                        raise LifecycleError('Native mount protections mismatch')
                    if root == 'output' and 'noexec' in data[root+'_options']:
                        raise LifecycleError('Reviewed Rust output is not executable')
                    if not 0 < data[root+'_bytes'] <= self._limits.scratch_bytes:
                        raise LifecycleError('Native tmpfs bounds mismatch')
            except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                raise LifecycleError('Malformed native canary data') from exc
            if self._limits.output_executable and any(data.get(k) is not True for k in ('output_fresh','output_exec','scratch_noexec')):
                raise LifecycleError('Rust writable executable scope mismatch')
        expected = {'uid': 65532, 'gid': 65532, 'root_write_denied': True,
                    'fresh': True, 'cap_eff': '0000000000000000', 'cap_bnd': '0000000000000000',
                    'nnp': '1', 'interfaces': ['lo'], 'socket_absent': True,
                    'memory': str(self._limits.memory_bytes), 'swap': '0',
                    'pids': str(self._limits.pids), 'tmp_type': 'tmpfs'}
        if any(data.get(k) != v for k,v in expected.items()):
            raise LifecycleError('Observed canary controls mismatch')
        self._validate_env([k+'='+v for k,v in data['env'].items()])
        cpu = [int(x) for x in data['cpu'].split()]
        if len(cpu) != 2 or cpu[1] <= 0 or cpu[0] <= 0 or cpu[0] / cpu[1] > self._limits.cpus:
            raise LifecycleError('Observed CPU cap mismatch')
        if not {'noexec','nosuid','nodev'} <= set(data['tmp_options']) or not 0 < data['tmp_bytes'] <= self._limits.scratch_bytes:
            raise LifecycleError('Observed scratch cap mismatch')
        return data

    def accept(self):
        if not self._lock.acquire(blocking=False):
            raise LifecycleError('Session is serial')
        self._accepted = None
        try:
            if self._poisoned:
                raise LifecycleError('Session poisoned')
            identity = self._identity(time.monotonic() + self._limits.wall_seconds)
            evidence = []
            for _ in range(2):
                result = self._lifecycle(self._canary_plan('policy'), runtime_id=identity)
                evidence.append({'worker': result.container_id, 'observations': self._check_canary(result)})
            timeout = self._lifecycle(self._canary_plan('timeout'), runtime_id=identity, wall=min(2.0, self._limits.wall_seconds))
            if not timeout.timed_out or not timeout.cleanup_ok:
                raise LifecycleError('Timeout/process-tree cleanup canary failed')
            output = self._lifecycle(self._canary_plan('output'), runtime_id=identity)
            if not output.truncated or len(output.output) != self._limits.output_bytes or not output.cleanup_ok:
                raise LifecycleError('Output ceiling canary failed')
            if identity != self._identity(time.monotonic() + self._limits.wall_seconds):
                raise LifecycleError('Runtime identity changed during acceptance')
            binding = tuple(policy_fingerprint(p, self._limits) for p in self._plans.values())
            report = {'runtime_id': identity, 'image_id': self._image, 'policy_digests': list(binding),
                      'canaries': evidence, 'timeout_cleanup': True, 'output_bounded': True,
                      'timeout_check': {'container_id': timeout.container_id, 'timed_out': timeout.timed_out,
                                        'cleanup_ok': timeout.cleanup_ok, 'elapsed_seconds': timeout.elapsed_seconds,
                                        'policy_digest': timeout.policy_digest},
                      'output_check': {'container_id': output.container_id, 'truncated': output.truncated,
                                       'output_bytes': len(output.output), 'cleanup_ok': output.cleanup_ok,
                                       'elapsed_seconds': output.elapsed_seconds, 'policy_digest': output.policy_digest},
                      'limitations': ['Evidence for tested controls only; not proof against container escapes.', 'Local trusted daemon/image/provisioning are part of the trust boundary.']}
            self._accepted = (identity, binding)
            return report
        finally:
            self._lock.release()

    def execute(self, operation_id: str, *, cancel=None):
        if type(operation_id) is not str or operation_id not in self._plans:
            raise SandboxPolicyError('Unknown provisioned operation ID')
        if not self._lock.acquire(blocking=False):
            raise LifecycleError('Session is serial')
        try:
            if self._accepted is None or self._poisoned:
                raise LifecycleError('Session requires independently executed canaries')
            binding = tuple(policy_fingerprint(p, self._limits) for p in self._plans.values())
            identity = self._identity(time.monotonic() + self._limits.wall_seconds)
            if self._accepted != (identity, binding):
                raise LifecycleError('Stale image/runtime/policy acceptance')
            return self._lifecycle(self._plans[operation_id], runtime_id=identity, cancel=cancel)
        except BaseException:
            self._accepted = None
            raise
        finally:
            self._lock.release()
