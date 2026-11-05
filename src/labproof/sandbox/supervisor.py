"""Bounded Docker CLI supervision; mocks prove controller logic, not containment.

The deadline starts before process creation, but an OS-stalled Popen itself cannot
be interrupted here. Killing the CLI is NOT container/process-tree cleanup. A
future accepted lifecycle controller must remove its owned container separately.
"""
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from typing import Callable

from .policy import (
    DOCKER_ENDPOINT, DOCKER_EXECUTABLE, REVIEWED_ENVIRONMENT,
    DockerCommand, SandboxLimits, SandboxPolicyError,
)


@dataclass(frozen=True)
class ProcessResult:
    output: bytes
    returncode: int | None
    timed_out: bool
    cancelled: bool
    truncated: bool
    cleanup_ok: bool
    error: str | None
    elapsed_seconds: float

    @property
    def ok(self) -> bool:
        return (self.returncode == 0 and not self.timed_out and not self.cancelled
                and not self.truncated and self.cleanup_ok and self.error is None)


class DockerSupervisor:
    """Serial trusted-host API, never exposed as a model tool.

    A private empty cwd/config disables inherited Docker contexts, credentials,
    plugins and proxy/provider environment. Only the fixed local endpoint and
    typed commands are admitted. Failed cleanup poisons this supervisor instance.
    """

    def __init__(self, limits: SandboxLimits = SandboxLimits(), *,
                 popen: Callable = subprocess.Popen,
                 clock: Callable[[], float] = time.monotonic):
        if type(limits) is not SandboxLimits:
            raise SandboxPolicyError("Expected sandbox limits")
        self.limits, self._popen, self._clock = limits, popen, clock
        self._serial = threading.Lock()
        self._poisoned = False

    def run(self, command: DockerCommand, *, cancel: threading.Event | None = None,
            deadline: float | None = None) -> ProcessResult:
        if type(command) is not DockerCommand:
            raise SandboxPolicyError("Only typed Docker controller commands are permitted")
        if deadline is not None and (type(deadline) not in (int, float) or
                                     not 0 <= deadline < float("inf")):
            raise SandboxPolicyError("Invalid absolute deadline")
        if not self._serial.acquire(blocking=False):
            raise SandboxPolicyError("Supervisor is serial")
        try:
            if self._poisoned:
                raise SandboxPolicyError("Previous cleanup failed; supervisor is blocked")
            return self._run(command, cancel, deadline)
        finally:
            self._serial.release()

    def _run(self, command, cancel, deadline):
        started = self._clock()
        end = min(started + self.limits.wall_seconds, deadline) if deadline is not None else started + self.limits.wall_seconds
        cancelled = cancel is not None and cancel.is_set()
        if cancelled or self._clock() >= end:
            return ProcessResult(b"", None, not cancelled, cancelled, False, True, None, 0.0)
        output = bytearray()
        lock = threading.Lock()
        finished = threading.Event()
        truncated = False
        read_failed = False
        proc = None
        reader = None
        error = None
        timed_out = False
        cleanup_ok = True
        # Controller-created directory, not a fixture directory or project cwd.
        with tempfile.TemporaryDirectory(prefix="labproof-controller-") as scratch:
            config = Path(scratch) / "docker-config"
            config.mkdir()
            env = dict(REVIEWED_ENVIRONMENT)
            env.update({"HOME": scratch, "USERPROFILE": scratch, "DOCKER_CONFIG": str(config),
                        "TEMP": scratch, "TMP": scratch, "TMPDIR": scratch})
            argv = (DOCKER_EXECUTABLE, "--config", str(config), "--host", DOCKER_ENDPOINT,
                    *command.arguments(self.limits))
            try:
                proc = self._popen(argv, shell=False, cwd=scratch, env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, bufsize=0, close_fds=True)

                def drain():
                    nonlocal truncated, read_failed
                    try:
                        while True:
                            chunk = proc.stdout.read(4096)
                            if not chunk:
                                break
                            with lock:
                                room = self.limits.output_bytes - len(output)
                                output.extend(chunk[:room])
                                truncated |= len(chunk) > room
                    except (OSError, ValueError):
                        read_failed = True
                    finally:
                        finished.set()

                reader = threading.Thread(target=drain, name="labproof-output", daemon=True)
                reader.start()
                while True:
                    cancelled = cancel is not None and cancel.is_set()
                    timed_out = self._clock() >= end
                    if cancelled or timed_out or read_failed or truncated:
                        break
                    if proc.poll() is not None and finished.is_set():
                        break
                    # Event.wait avoids an output-dependent deadline / busy loop.
                    time.sleep(min(0.01, max(0, end - self._clock())))
            except (OSError, ValueError) as exc:
                error = f"process_start_or_io_failed:{type(exc).__name__}"
            finally:
                cleanup_end = self._clock() + self.limits.cleanup_seconds
                if proc is not None:
                    try:
                        if proc.poll() is None:
                            proc.kill()
                        proc.wait(timeout=max(0, cleanup_end - self._clock()))
                    except (OSError, subprocess.TimeoutExpired):
                        cleanup_ok = False
                    if reader is not None:
                        reader.join(timeout=max(0, cleanup_end - self._clock()))
                        if reader.is_alive():
                            # Do not close a pipe underneath a blocked read: that
                            # can itself block. Poison and expose failed cleanup.
                            cleanup_ok = False
                    if reader is None or not reader.is_alive():
                        if proc.stdout is not None:
                            proc.stdout.close()
                if not cleanup_ok:
                    self._poisoned = True
            if read_failed:
                error = "output_read_failed"
            with lock:
                captured = bytes(output)
            return ProcessResult(captured, proc.returncode if proc is not None else None,
                                 timed_out, cancelled, truncated, cleanup_ok, error,
                                 max(0, self._clock() - started))
