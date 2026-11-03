"""Run a supervisor in a process of its own.

In the simulator's process a supervisor can reach the simulator's state (through the call stack, for example) and
read the ground truth. In its own process it gets only what the protocol sends it, as JSON: observations, contexts,
answers and outcomes; and it answers in JSON, so it cannot run code in the simulator's process either.

The child starts with nothing of the parent's but the path to import from: its own command line, an empty
environment, and an empty temporary working directory that is deleted after the episode. Every call has a time limit
and every reply a size limit; a supervisor that breaks them is killed and the run fails with `SupervisorError`.

This keeps an honest supervisor honest, and stops the easy ways to cheat, but it is not a sandbox: the child runs as
the same user and can read whatever that user can, and could look at other processes. Processes it starts are
killed with it if they stay in its process group; one that moves to a group of its own survives. Scores from
untrusted code need an OS sandbox around it (a container or a separate user without access to the key or the
results).
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

from .model import Answer, Context, Decision, Details, Observation, Outcome, PendingQuestion

MAX_REPLY = 1 << 16
MAX_NAME = 64
MAX_REPORTED = 1e12
REPORT_KEY = re.compile(r'[A-Za-z0-9_.:-]{1,64}')


class SupervisorError(RuntimeError):
    """An isolated supervisor crashed, hung, or broke the protocol."""


# ---- the wire format: dataclasses as JSON objects, tuples as lists

def _encode(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {f.name: _encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    return value


def _observation(data: dict[str, Any]) -> Observation:
    return Observation(**{**data, 'cell': tuple(data['cell']), 'target': tuple(data['target']),
                          'actions': tuple(data['actions']), 'details': Details(data['details'])})


def _context(data: dict[str, Any]) -> Context:
    pending = tuple(PendingQuestion(q['id'], q['kind'], tuple(q['target']), tuple(q['incidents']), q['asked_at'])
                    for q in data['pending'])
    return Context(data['time'], pending, data['human_queue'])


def _arguments(method: str, args: list[Any]) -> list[Any]:
    if method == 'decide':
        return [_observation(args[0]), _context(args[1])]
    if method == 'on_answer':
        return [_observation(args[0]), Answer(**args[1])]
    if method == 'on_outcome':
        return [_observation(args[0]), Outcome(**args[1])]
    return args


# ---- the child

def _serve() -> None:
    """The child's main loop: one JSON request per line on stdin, one JSON reply per line on the original stdout.
    The supervisor's own prints go to stderr."""
    out = os.fdopen(os.dup(1), 'wb')
    os.dup2(2, 1)
    first = json.loads(sys.stdin.readline())
    sys.path[:0] = first['path']
    from .supervisors import by_name
    supervisor = by_name(first['spec'])

    def reply(value: Any) -> None:
        out.write(json.dumps(value).encode() + b'\n')
        out.flush()

    reply(str(supervisor.name)[:MAX_NAME])
    for line in sys.stdin:
        method, args = json.loads(line)
        if method == 'report':
            report = getattr(supervisor, 'report', None)
            reply(report() if report else {})
            continue
        result = getattr(supervisor, method)(*_arguments(method, args))
        reply([result.type, result.action, result.question] if method == 'decide' else None)


# ---- the parent

def _no_constant(name: str) -> None:
    raise ValueError(f'{name} is not a number')


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + '...'


class Isolated:
    """A supervisor proxy: `spec` is anything `supervisors.by_name` accepts, including `module:Class`, importable
    from `path` (where this process imports from, by default). `timeout` limits each call, sending included, and
    `start_timeout` the start. Its `name` is the spec, whatever the supervisor calls itself, so a submission cannot
    pass itself off as a baseline in the results."""

    def __init__(self, spec: str, timeout: float = 10.0, start_timeout: float = 60.0,
                 path: list[str] | None = None) -> None:
        self.spec, self.name, self.timeout = spec, spec, timeout
        self._buffer = b''
        self.process, self._closed = None, False
        self.workdir = tempfile.mkdtemp(prefix='fleetattention-')
        package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            # A session of its own, so that close() can kill whatever processes the supervisor started too.
            self.process = subprocess.Popen(
                [sys.executable, '-I', '-c', f'import sys; sys.path.insert(0, {package_root!r}); '
                 'from fleetattention.isolate import _serve; _serve()'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=self.workdir, env={}, start_new_session=True,
            )
        except BaseException:
            shutil.rmtree(self.workdir, ignore_errors=True)
            raise
        try:
            os.set_blocking(self.process.stdin.fileno(), False)
            # The paths to import the supervisor from come in the first message.
            if path is None:
                path = [os.path.abspath(entry or os.curdir) for entry in sys.path]
            self._send({'spec': spec, 'path': path}, time.monotonic() + start_timeout)
            name = self._receive(time.monotonic() + start_timeout, start_timeout)
            if not isinstance(name, str):
                self._fail(f'sent {_short(name)} as its name')
        except BaseException:
            self.close()
            raise

    def _send(self, message: Any, deadline: float) -> None:
        """Write one request without ever blocking past the deadline. Every reply must answer a request: anything
        the supervisor sent before being asked is refused, so it cannot run ahead of the simulator."""
        stdin, stdout = self.process.stdin.fileno(), self.process.stdout.fileno()
        if self._buffer or select.select([stdout], [], [], 0)[0]:
            if self._buffer or os.read(stdout, 1):
                self._fail('replied out of turn')
            self._fail('exited')
        data = json.dumps(message).encode() + b'\n'
        while data:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([], [stdin], [], left)[1]:
                self._fail(f'did not take a request within {self.timeout:g} s')
            try:
                data = data[os.write(stdin, data):]
            except BlockingIOError:
                continue
            except OSError:
                self._fail('exited')

    def _receive(self, deadline: float, timeout: float) -> Any:
        stdout = self.process.stdout.fileno()
        while b'\n' not in self._buffer:
            if len(self._buffer) > MAX_REPLY:
                self._fail(f'sent a reply longer than {MAX_REPLY} bytes')
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([stdout], [], [], left)[0]:
                self._fail(f'did not reply within {timeout:g} s')
            chunk = os.read(stdout, MAX_REPLY)
            if not chunk:
                self._fail('exited')
            self._buffer += chunk
        line, self._buffer = self._buffer.split(b'\n', 1)
        if self._buffer:
            self._fail('sent more than one reply')
        if len(line) > MAX_REPLY:
            self._fail(f'sent a reply longer than {MAX_REPLY} bytes')
        try:
            return json.loads(line, parse_constant=_no_constant)
        except ValueError:
            self._fail('sent a reply that is not JSON')

    def _fail(self, what: str) -> None:
        self.close()
        raise SupervisorError(f'supervisor {self.spec!r} {what}')

    def _call(self, method: str, *args: Any) -> Any:
        if self._closed:
            raise SupervisorError(f'supervisor {self.spec!r} was already closed')
        deadline = time.monotonic() + self.timeout
        self._send([method, [_encode(a) for a in args]], deadline)
        return self._receive(deadline, self.timeout)

    def reset(self, seed: int) -> None:
        self._call('reset', seed)

    def decide(self, obs: Observation, ctx: Context) -> Decision:
        reply = self._call('decide', obs, ctx)
        valid = isinstance(reply, list) and len(reply) == 3 and (
            reply[0] == 'act' and isinstance(reply[1], str) and reply[2] is None
            or reply[0] == 'ask' and reply[1] is None and reply[2] is None
            or reply[0] == 'join' and reply[1] is None and type(reply[2]) is int)
        if not valid:
            self._fail(f'returned {_short(reply)}, not a Decision')
        return Decision(*reply)

    def on_answer(self, obs: Observation, answer: Answer) -> None:
        self._call('on_answer', obs, answer)

    def on_outcome(self, obs: Observation, outcome: Outcome) -> None:
        self._call('on_outcome', obs, outcome)

    def report(self) -> dict[str, float]:
        """The supervisor's own counters, if it has a `report()` method: plain names (letters, digits, `_.:-`) and
        finite numbers only, so that nothing in it can break the results files."""
        reply = self._call('report')
        if not isinstance(reply, dict) or not all(
                REPORT_KEY.fullmatch(k) and type(v) in (int, float) and abs(v) <= MAX_REPORTED
                for k, v in reply.items()):
            self._fail(f'returned {_short(reply)} as its report')
        return {k: float(v) for k, v in reply.items()}

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.process is not None:
            if self.process.poll() is None:
                try:
                    # End of input: an honest supervisor exits now. Requests are written with os.write, so the
                    # file object has nothing buffered and closing it cannot block.
                    self.process.stdin.close()
                except OSError:
                    pass
                try:
                    self.process.wait(1)
                except subprocess.TimeoutExpired:
                    pass
            try:
                os.killpg(self.process.pid, signal.SIGKILL)  # the supervisor and anything it started
            except (ProcessLookupError, PermissionError):
                pass
            self.process.wait()
            for stream in (self.process.stdin, self.process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass
        shutil.rmtree(self.workdir, ignore_errors=True)

    def __enter__(self) -> Isolated:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
