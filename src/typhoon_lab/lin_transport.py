"""Vendor-independent LIN master contract and deterministic test doubles.

No SDK is imported. A future driver implements whole-frame publication and
header/response requests; it owns wire timing and bounded native calls.
"""
from collections import deque
from dataclasses import dataclass
import math
from typing import Protocol

from .tle9877 import FRAME_ALIASES, byte_values, pid


class LINTransportError(RuntimeError):
    pass


class LINTimeout(TimeoutError):
    pass


@dataclass(frozen=True)
class LINFrame:
    pid: int
    data: tuple
    checksum: int
    device_time_s: float | None
    clock_domain: str
    driver_status: str = 'ok'

    def raw(self):
        return {'pid': self.pid, 'data': list(self.data), 'checksum': self.checksum,
                'device_time_s': self.device_time_s, 'clock_domain': self.clock_domain,
                'driver_status': self.driver_status}


class LINClock(Protocol):
    domain: str

    def monotonic(self) -> float: ...
    def sleep_until(self, deadline_s: float) -> None: ...


class LINMaster(Protocol):
    """Frame IDs here are six-bit IDs; received frames carry the actual PID.

    publish returns local TX completion, not proof of reception by the board.
    request sends a header, then returns raw response bytes or raises LINTimeout.
    Both methods must finish within timeout_s, including native SDK waits. The
    driver must not silently repair PID/checksum errors or automatically retry.
    close releases the adapter; board stop/postrun is a separate procedure.
    """
    backend: str
    device_id: str

    def open(self, *, bitrate: int) -> None: ...
    def wake_up(self) -> None: ...
    def publish(self, frame_id: int, data: tuple, checksum: int, *, timeout_s: float) -> LINFrame: ...
    def request(self, frame_id: int, length: int, *, timeout_s: float) -> LINFrame: ...
    def close(self) -> None: ...


class MockClock:
    domain = 'mock_monotonic'

    def __init__(self):
        self.time_s = 0.0

    def monotonic(self):
        return self.time_s

    def sleep_until(self, deadline_s):
        self.time_s = max(self.time_s, deadline_s)

    def advance(self, seconds):
        self.time_s += seconds


def validate_steps(steps):
    if not isinstance(steps, list) or not steps or len(steps) > 1000:
        raise ValueError('mock steps must be a list of 1..1000 exchanges')
    for step in steps:
        if not isinstance(step, dict) or step.get('operation') not in ('publish', 'request'):
            raise ValueError('each step needs a publish/request operation')
        if step.get('frame') not in FRAME_ALIASES or step.get('outcome') not in ('ok', 'timeout', 'transport_error'):
            raise ValueError('mock step frame/outcome is unsupported')
        delay = step.get('delay_s', 0)
        if type(delay) not in (int, float) or not math.isfinite(delay) or delay < 0:
            raise ValueError('mock delay_s must be finite and nonnegative')
        if step['outcome'] == 'ok':
            if step['operation'] == 'request':
                byte_values(step.get('data'))
                fields = ('pid', 'checksum')
            else:
                byte_values(step.get('expected_data'))
                fields = ('expected_checksum',)
            if any(type(step.get(k)) is not int or not 0 <= step[k] <= 255 for k in fields):
                raise ValueError('raw PID/checksum must be integer bytes')


class MockLINMaster:
    backend = 'mock'
    device_id = 'mock:master'

    def __init__(self, steps, clock):
        validate_steps(steps)
        self.steps = deque(steps)
        self.clock = clock
        self.calls = []
        self.is_open = False

    def open(self, *, bitrate):
        if self.is_open or bitrate != 19200:
            raise LINTransportError('mock expects one open at 19200 bit/s')
        self.calls.append({'operation': 'open', 'bitrate': bitrate})
        self.is_open = True

    def wake_up(self):
        if not self.is_open:
            raise LINTransportError('adapter is closed')
        self.calls.append({'operation': 'wake_up'})

    def _step(self, operation, frame_id, timeout_s):
        if not self.is_open or not self.steps:
            raise LINTransportError('adapter closed or mock script exhausted')
        step = self.steps.popleft()
        expected_id = {'control': 38, 'status': 37, 'version': 39}[step['frame']]
        if step['operation'] != operation or frame_id != expected_id:
            raise LINTransportError('operation/frame differs from independent mock script')
        self.calls.append({'operation': operation, 'id': frame_id, 'time_s': self.clock.monotonic()})
        delay = step.get('delay_s', 0)
        if step['outcome'] == 'timeout' or delay > timeout_s:
            self.clock.advance(timeout_s)
            raise LINTimeout(f'ID 0x{frame_id:02X} timed out after {timeout_s}s')
        self.clock.advance(delay)
        if step['outcome'] == 'transport_error':
            raise LINTransportError('injected adapter disconnect/error')
        return step

    def publish(self, frame_id, data, checksum, *, timeout_s):
        step = self._step('publish', frame_id, timeout_s)
        if list(data) != byte_values(step['expected_data']) or checksum != step['expected_checksum']:
            raise LINTransportError('TX bytes/checksum differ from independent expected vector')
        return LINFrame(pid(frame_id), tuple(data), checksum, self.clock.monotonic(), self.clock.domain)

    def request(self, frame_id, length, *, timeout_s):
        step = self._step('request', frame_id, timeout_s)
        # Deliberately preserve bad lengths, PID and checksum for client checks.
        return LINFrame(step['pid'], tuple(byte_values(step['data'])), step['checksum'],
                        self.clock.monotonic(), self.clock.domain)

    def close(self):
        self.calls.append({'operation': 'close'})
        self.is_open = False
