"""Optional Windows MXC boundary for evaluator trials; never a skill runtime.

Requires codex-cli with explicit native MXC and OMP's extension/RPC API.
No fallback: preflight must prove filesystem and network restrictions first.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

_LIMIT = 16 * 1024 * 1024
# Pinned trial model; override when the host retires it (list: `omp models`).
_MODEL = os.environ.get('YEET_TRIAL_MODEL', 'anthropic/claude-sonnet-5-5')
_ready = False
_lock = threading.Lock()


def _environment() -> dict[str, str]:
    # Deliberately exclude API keys, proxy overrides, Python/Node startup hooks,
    # ORCA hooks and provider tokens. Stored OMP authentication stays with OMP.
    keys = {'SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC', 'PATHEXT',
            'LOCALAPPDATA', 'USERPROFILE'}
    env = {k: v for k, v in os.environ.items() if k.upper() in keys}
    windows = Path(env.get('SYSTEMROOT', 'C:/Windows'))
    codex = shutil.which('codex')
    paths = [str(Path(sys.executable).parent), str(windows / 'System32'), str(windows)]
    if codex:
        paths.append(str(Path(codex).parent))
    env['PATH'] = os.pathsep.join(paths)
    return env


class _Job:
    """Kill-on-close Windows job, assigned before the suspended child starts."""
    def __init__(self):
        if sys.platform != 'win32':
            raise RuntimeError('Trials require Windows native MXC; no fallback is permitted')
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.k.CreateJobObjectW.restype = wintypes.HANDLE
        self.k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.k.CreateJobObjectW(None, None)
        # JOBOBJECT_EXTENDED_LIMIT_INFORMATION (64-bit Windows layout).
        class Basic(ctypes.Structure):
            _fields_ = [('user', ctypes.c_int64), ('job', ctypes.c_int64), ('flags', wintypes.DWORD),
                        ('minimum', ctypes.c_size_t), ('maximum', ctypes.c_size_t),
                        ('active', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                        ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class Limits(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.k.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def start(self, argv, cwd, env):
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=0x4 | subprocess.CREATE_NO_WINDOW)
        try:
            if not self.k.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(p._handle))):
                raise ctypes.WinError(ctypes.get_last_error())
            resume = ctypes.WinDLL('ntdll').NtResumeProcess
            resume.argtypes = [wintypes.HANDLE]
            resume.restype = ctypes.c_long
            if resume(wintypes.HANDLE(int(p._handle))) != 0:
                raise RuntimeError('Cannot resume job-contained trial process')
            return p
        except BaseException:
            p.kill()
            p.wait()
            raise

    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None


class _Capture:
    def __init__(self, p):
        self.events = queue.Queue()
        self.out = bytearray()
        self.err = bytearray()
        self.overflow = threading.Event()
        self.threads = []
        for name, stream, data in [('out', p.stdout, self.out), ('err', p.stderr, self.err)]:
            thread = threading.Thread(target=self._read, args=(name, stream, data), daemon=True)
            thread.start()
            self.threads.append(thread)

    def _read(self, name, stream, data):
        pending = bytearray()
        while chunk := stream.read1(4096):
            if len(data) + len(chunk) > _LIMIT:
                self.overflow.set()
                return
            data.extend(chunk)
            if name == 'out':
                pending.extend(chunk)
                while (end := pending.find(b'\n')) >= 0:
                    self.events.put(bytes(pending[:end + 1]))
                    del pending[:end + 1]
        self.events.put(None)

    def finish(self):
        for thread in self.threads:
            thread.join(5)
        if any(t.is_alive() for t in self.threads):
            raise RuntimeError('Trial child pipes did not close after job termination')
        if self.overflow.is_set():
            raise RuntimeError(f'Trial output exceeded {_LIMIT} bytes per stream; process tree terminated')
        return self.out.decode('utf-8', 'replace'), self.err.decode('utf-8', 'replace')


def _sandbox(root: Path, code: str, timeout: int) -> subprocess.CompletedProcess[str]:
    root = root.resolve(strict=True)
    codex = shutil.which('codex')
    if not codex:
        raise RuntimeError('Install a codex-cli supporting windows.sandbox=mxc; no sandbox fallback allowed')
    with tempfile.TemporaryDirectory(prefix='yeet-mxc-profile-') as profile:
        scratch = Path(profile) / 'scratch'
        scratch.mkdir()
        env = _environment() | {'CODEX_HOME': profile, 'TEMP': str(scratch),
                                'TMP': str(scratch), 'TRIAL_SCRATCH': str(scratch)}
        runtime = Path(sys.base_prefix).resolve().as_posix()
        permissions = 'permissions={trial={filesystem={":root"="deny",":minimal"="read",' + json.dumps(runtime) + '="read",' + json.dumps(scratch.as_posix()) + '="write",":workspace_roots"={"."="read"}},network={enabled=false}}}'
        argv = [codex, '-c', 'windows.sandbox=mxc', '-c', permissions, 'sandbox',
                '--include-managed-config', '--permission-profile', 'trial', '-C', str(root),
                '--', sys.executable, '-E', '-s', '-B', '-X', 'utf8', '-c', code]
        job = _Job()
        capture = None
        try:
            p = job.start(argv, root, env)
            p.stdin.close()
            capture = _Capture(p)
            deadline = time.monotonic() + timeout
            while p.poll() is None:
                if capture.overflow.wait(.02):
                    raise RuntimeError('Trial output limit exceeded; process tree terminated')
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(argv, timeout)
            status = p.returncode
        finally:
            job.close()
            if capture:
                stdout, stderr = capture.finish()
        return subprocess.CompletedProcess(argv, status, stdout, stderr)


def preflight() -> None:
    """Prove workspace-read, scratch-write, sibling denial and denied network."""
    global _ready
    with _lock:
        if _ready:
            return
        if sys.platform != 'win32':
            raise RuntimeError('Behavioural trials require Windows MXC; no fallback allowed')
        # Pinned public endpoint: TCP only, no credentials or application data.
        endpoint = ('1.1.1.1', 443)
        try:
            with socket.create_connection(endpoint, timeout=5):
                pass
        except OSError as error:
            raise RuntimeError('MXC preflight cannot prove network denial: outside TCP control 1.1.1.1:443 failed; restore connectivity and retry') from error
        with tempfile.TemporaryDirectory(prefix='yeet-boundary-') as folder:
            parent = Path(folder)
            root = parent / 'workspace'
            root.mkdir()
            (root / 'inside').write_text('inside-canary', encoding='utf-8')
            sibling = parent / 'sibling'
            sibling.write_text('sibling-canary', encoding='utf-8')
            marker = secrets.token_hex(24)
            code = f'''from pathlib import Path
import os, socket
assert Path('inside').read_text() == 'inside-canary'
scratch = Path(os.environ['TRIAL_SCRATCH'])
(scratch / 'written').write_text('scratch-write')
assert (scratch / 'written').read_text() == 'scratch-write'
sibling = Path({str(sibling)!r})
for action in (lambda: Path('inside').write_text('ESCAPE'), lambda: Path('written').write_text('ESCAPE'), lambda: sibling.read_bytes(), lambda: sibling.write_text('ESCAPE'), lambda: sibling.with_name('new-sibling').write_text('ESCAPE')):
    try:
        action()
    except PermissionError:
        pass
    else:
        raise RuntimeError('Workspace write or sibling filesystem access was not denied')
try:
    socket.create_connection({endpoint!r}, timeout=3)
except OSError:
    pass
else:
    raise RuntimeError('Network access was not denied')
print({marker!r})
'''
            proc = _sandbox(root, code, 30)
            if proc.returncode != 0 or proc.stdout.splitlines()[-1:] != [marker]:
                raise RuntimeError(f'MXC preflight failed; explicit native MXC and managed policy must support root-deny, workspace-read, scratch-write, Python-read and network-off. Exit {proc.returncode}: {proc.stderr or proc.stdout}')
            if sibling.read_text() != 'sibling-canary' or (parent / 'new-sibling').exists() or (root / 'written').exists() or (root / 'inside').read_text() != 'inside-canary':
                raise RuntimeError('MXC read-only workspace or sibling canary changed')
        _ready = True


def python_process(root: Path, code: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Execute inside MXC with read-only workspace and disposable writable scratch."""
    preflight()
    return _sandbox(root, code, timeout)


def require_completed_turn(event: dict, assistant: dict | None) -> None:
    """Reject interrupted RPC turns even when their intermediate checks passed."""
    if event.get('agentInvoked') is not True or event.get('status') != 'completed' or event.get('sessionSettled') is not True:
        raise RuntimeError(f'Trial did not complete: {event.get("status")}')
    if not isinstance(assistant, dict) or assistant.get('role') != 'assistant' or assistant.get('stopReason') != 'stop':
        raise RuntimeError('Trial has no successful terminal assistant message')
    content = assistant.get('content')
    if not isinstance(content, list) or not any(
        part.get('type') == 'text' and isinstance(part.get('text'), str) and part['text'].strip()
        for part in content if isinstance(part, dict)
    ):
        raise RuntimeError('Trial has no terminal result text')


def agent_process(root: Path, prompt: str, local_only: bool, results_dir: Path) -> subprocess.CompletedProcess[str]:
    """RPC agent with a nonce-verified deny-all-except-trial-tools extension."""
    preflight()
    root = root.resolve(strict=True)
    runtime = shutil.which('omp')
    if not runtime:
        raise RuntimeError('OMP CLI unavailable; install a version supporting extensions and RPC')
    nonce = secrets.token_hex(24)
    guard = Path(__file__).with_name('trial_guard.ts').resolve(strict=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='yeet-omp-') as temporary:
        env = _environment()
        for key in ('USERPROFILE', 'HOME', 'HOMEDRIVE', 'HOMEPATH', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA'):
            if key in os.environ:
                env[key] = os.environ[key]
        env.update({'TEMP': temporary, 'TMP': temporary, 'TRIAL_ROOT': str(root),
                    'TRIAL_NONCE': nonce, 'TRIAL_LOCAL_ONLY': '1' if local_only else '0',
                    'TRIAL_PYTHON': sys.executable, 'TRIAL_BOUNDARY': str(Path(__file__).resolve()),
                    'TRIAL_CHILD_ENV': json.dumps(_environment())})
        config = Path(temporary) / 'trial.yml'
        # Local authorisation covers only the fixed sandboxed fixture tool, not
        # arbitrary exec tools or provider safety checks.
        config.write_text('mcp:\n  enableProjectConfig: false\ntools:\n  approval:\n    trial_check: allow\n', encoding='utf-8')
        argv = [runtime, '--mode', 'rpc', '--no-ui', '--no-session', '--no-context-files',
                '--no-skills', '--no-rules', '--no-extensions', '--no-lsp', '--no-pty',
                '--no-tools', '--extension', str(guard), '--config', str(config),
                '--model', _MODEL, '--thinking', 'low', '--no-title',
                '--max-time', '600', '--cwd', str(root), '--approval-mode', 'write']
        job = _Job()
        capture = None
        try:
            p = job.start(argv, root, env)
            capture = _Capture(p)
            def send(value):
                p.stdin.write((json.dumps(value) + '\n').encode('utf-8'))
                p.stdin.flush()
            def receive(deadline):
                while time.monotonic() < deadline:
                    if capture.overflow.is_set():
                        raise RuntimeError('OMP output exceeded capture limit')
                    try:
                        line = capture.events.get(timeout=.1)
                    except queue.Empty:
                        if p.poll() is not None:
                            detail = bytes(capture.err[-2000:]).decode('utf-8', 'replace').strip()
                            raise RuntimeError(f'OMP exited {p.returncode} before RPC completion: {detail}')
                        continue
                    if line is not None:
                        try:
                            return json.loads(line)
                        except ValueError as error:
                            raise RuntimeError('OMP emitted non-JSON stdout; cannot prove guard readiness') from error
                raise RuntimeError('OMP RPC deadline exceeded; child tree terminated')
            send({'id': 'guard', 'type': 'get_available_commands'})
            handshake_deadline = time.monotonic() + 45
            while True:
                event = receive(handshake_deadline)
                if event.get('type') == 'response' and event.get('id') == 'guard':
                    commands = event.get('data', {}).get('commands', [])
                    if not event.get('success') or not any(c.get('name') == 'trial_guard_' + nonce for c in commands):
                        raise RuntimeError('OMP guard handshake missing; no model prompt sent. Check extension load errors and supported RPC API')
                    break
            instruction = ('Use only trial_read, trial_write and (coding tasks) trial_check. '
                           'First read .agents/skills/yeet/SKILL.md. No other tools, external actions or delegation. '
                           'trial_check executes the immutable original task fixture in a network-disabled MXC sandbox. ' + prompt)
            # Prefix prevents user text beginning with / from becoming a local RPC slash command.
            send({'id': 'trial', 'type': 'prompt', 'message': instruction})
            deadline = time.monotonic() + 610
            last_assistant = None
            while True:
                event = receive(deadline)
                if event.get('type') == 'message_end':
                    message = event.get('message')
                    if isinstance(message, dict) and message.get('role') == 'assistant':
                        last_assistant = message
                if event.get('type') == 'response' and event.get('id') == 'trial' and not event.get('success'):
                    raise RuntimeError(f'OMP rejected trial prompt: {event}')
                if event.get('type') == 'prompt_result' and event.get('id') == 'trial':
                    require_completed_turn(event, last_assistant)
                    break
            p.stdin.close()
            p.wait(timeout=15)
            status = p.returncode
        finally:
            job.close()
            if capture:
                stdout, stderr = capture.finish()
                (results_dir / f'boundary-{nonce}.jsonl').write_text(stdout, encoding='utf-8')
                (results_dir / f'boundary-{nonce}.stderr.log').write_text(stderr, encoding='utf-8')
        return subprocess.CompletedProcess(argv, status, stdout, stderr)


def _check(root: Path, fixture: str, expected: str) -> int:
    preflight()
    if fixture not in ('test_names.py', 'test_dates.py'):
        raise RuntimeError('Only fixed trial fixtures may execute')
    target = root / fixture
    metadata = target.lstat()
    if metadata.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Immutable trial fixture changed')
    marker = 'TRIAL_CHECK_' + secrets.token_hex(24)
    code = f'import runpy\nrunpy.run_path({fixture!r}, run_name="__main__")\nprint({marker!r})'
    proc = python_process(root, code)
    completed = proc.returncode == 0 and proc.stdout.splitlines()[-1:] == [marker]
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Fixture changed during check')
    print(json.dumps({'fixture': fixture, 'exitCode': proc.returncode, 'completed': completed,
                      'stdout': proc.stdout, 'stderr': proc.stderr}))
    return 0


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--check':
        sys.exit(_check(Path(sys.argv[2]), sys.argv[3], sys.argv[4]))
    raise SystemExit('Internal interface: import preflight/python_process/agent_process; CLI accepts only --check ROOT FIXTURE SHA256')
