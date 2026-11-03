"""LDF-based schedule orchestration and inspectable offline mock bus logs."""
from pathlib import Path
import json
import math
import shutil

from .cases import read_json
from .lin_transport import LINMaster, LINClock, MockClock, MockLINMaster, LINTimeout, LINTransportError, validate_steps
from .tle9877 import DEFAULT_PROFILE, FRAME_ALIASES, decode_frame, encode_control, load_profile
from .utils import PROJECT, new_run, now, sha256, write_json


def validate_scenario(scenario, profile_path=DEFAULT_PROFILE):
    if (not isinstance(scenario, dict) or type(scenario.get('schema_version')) is not int
            or scenario['schema_version'] != 1 or scenario.get('scope') != 'mock_only'):
        raise ValueError('scenario must be schema_version 1, scope=mock_only')
    encode_control(scenario.get('rpm'), scenario.get('post_set'), profile_path=profile_path)
    if type(scenario.get('cycles')) is not int or not 1 <= scenario['cycles'] <= 100:
        raise ValueError('cycles must be an integer in 1..100')
    if any(type(scenario.get(key)) is not bool for key in ('read_version', 'wake_up')):
        raise ValueError('read_version and wake_up must be booleans')
    timeout = scenario.get('response_timeout_s')
    _, ldf = load_profile(profile_path)
    raw_slots = next(t['schedule'] for t in ldf['schedule_tables'] if t['name'] == 'EWPTEST')
    if any(s['command']['type'] != 'frame' for s in raw_slots):
        raise ValueError('EWPTEST must contain ordinary frame slots')
    slots = [{'frame': s['command']['frame'], 'delay': s['delay']} for s in raw_slots]
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout < min(s['delay'] for s in slots):
        raise ValueError('response_timeout_s must be positive and shorter than an EWPTEST slot')
    validate_steps(scenario.get('steps'))
    return slots


def exchange_schedule(master: LINMaster, clock: LINClock, scenario, *, profile_path=DEFAULT_PROFILE):
    """Stop on the first bus/schedule error; always attempt adapter release.

    The host supplies deadlines. A vendor driver must implement bounded calls;
    this Python loop is not a wire-level or real-time feedback implementation.
    """
    slots = validate_scenario(scenario, profile_path)
    _, ldf = load_profile(profile_path)
    frames = {f['name']: f for f in ldf['frames']}
    aliases = {value: key for key, value in FRAME_ALIASES.items()}
    control = encode_control(scenario['rpm'], scenario['post_set'], profile_path=profile_path)
    timeout = scenario['response_timeout_s']
    cycle_s = sum(s['delay'] for s in slots)
    initial_time = clock.monotonic()
    journal = []
    failure = None

    def record(event, **fields):
        value = {'sequence': len(journal), 'event': event, 'logged_at': now(),
                 'session_time_s': clock.monotonic() - initial_time,
                 'host_clock_domain': clock.domain, **fields}
        journal.append(value)
        return value

    def exchange(name, scheduled):
        frame = frames[name]
        publishing = frame['publisher'] == 'ECU'
        operation = 'publish' if publishing else 'request'
        entry = record('exchange', operation=operation, frame=name, id=frame['frame_id'],
                       scheduled_time_s=scheduled - initial_time,
                       actual_start_time_s=clock.monotonic() - initial_time,
                       timeout_s=timeout, status='pending')
        if publishing:
            entry['tx_requested'] = {'pid': control['pid'], 'data': control['data'], 'checksum': control['checksum']}
        try:
            if publishing:
                if name != 'ControlLIN':
                    raise LINTransportError('no publication encoder for this frame')
                raw = master.publish(frame['frame_id'], tuple(control['data']), control['checksum'], timeout_s=timeout)
            else:
                raw = master.request(frame['frame_id'], frame['length'], timeout_s=timeout)
            entry['raw'] = raw.raw()
            if clock.monotonic() - initial_time - entry['actual_start_time_s'] > timeout + 1e-9:
                raise LINTimeout('driver returned after exchange timeout')
            if raw.driver_status != 'ok':
                raise LINTransportError(f'driver receive/transmit status: {raw.driver_status}')
            decoded = decode_frame(aliases[name], raw.data, identifier=raw.pid, identifier_kind='pid',
                                   received_checksum=raw.checksum, profile_path=profile_path)
            if publishing and (list(raw.data) != control['data'] or raw.checksum != control['checksum']):
                raise LINTransportError('local TX completion differs from requested bytes')
            entry.update(status='passed', decoded=decoded,
                         meaning='local_tx_completed' if publishing else 'response_received')
        except Exception as exc:
            entry.update(status='failed', error={'code': type(exc).__name__, 'message': str(exc)})
            raise
        finally:
            entry['completed_time_s'] = clock.monotonic() - initial_time

    try:
        record('open_requested', bitrate=ldf['speed'], backend=master.backend, device_id=master.device_id)
        master.open(bitrate=ldf['speed'])
        record('opened')
        if scenario['wake_up']:
            record('wake_up_requested')
            master.wake_up()
            record('wake_up_completed')
        if scenario['read_version']:
            exchange('VARIANTLIN', clock.monotonic())
        base = clock.monotonic()
        for cycle in range(scenario['cycles']):
            offset = 0.0
            for slot in slots:
                due = base + cycle * cycle_s + offset
                if clock.monotonic() > due + 1e-9:
                    raise LINTransportError('schedule deadline missed; no catch-up burst or automatic retry')
                clock.sleep_until(due)
                if clock.monotonic() > due + 1e-9:
                    raise LINTransportError('schedule wake-up was late; frame not started')
                exchange(slot['frame'], due)
                if clock.monotonic() > due + slot['delay'] + 1e-9:
                    raise LINTransportError('exchange overran its LDF slot')
                offset += slot['delay']
            # Keep the last slot too: the session covers complete schedule cycles.
            clock.sleep_until(base + (cycle + 1) * cycle_s)
        record('schedule_completed', cycles=scenario['cycles'], cycle_s=cycle_s)
    except Exception as exc:
        failure = {'code': type(exc).__name__, 'message': str(exc)}
        record('session_error', error=failure)
    finally:
        record('close_requested')
        try:
            master.close()
            record('closed')
        except Exception as exc:
            close_error = {'code': type(exc).__name__, 'message': str(exc)}
            record('close_error', error=close_error)
            failure = failure or close_error
    return {'status': 'failed' if failure else 'passed', 'error': failure, 'journal': journal,
            'ldf_schedule': {'name': 'EWPTEST', 'cycle_s': cycle_s, 'slots': slots},
            'requested_rpm': control['requested_rpm'], 'encoded_rpm': control['encoded_rpm'],
            'model_speed_rpm': None, 'host_clock_domain': clock.domain,
            'clock_synchronization': 'not_established', 'backend': master.backend}


def run_mock_scenario(scenario_path, output_dir=None, *, profile_path=DEFAULT_PROFILE):
    scenario_path = Path(scenario_path)
    scenario = read_json(scenario_path)
    validate_scenario(scenario, profile_path)
    clock = MockClock()
    master = MockLINMaster(scenario['steps'], clock)
    started_at = now()
    if output_dir is None:
        output = new_run('lin-mock')
    else:
        output = Path(output_dir)
        # A replay creates a new package and never overwrites an earlier log.
        output.mkdir(parents=True, exist_ok=False)
    result = exchange_schedule(master, clock, scenario, profile_path=profile_path)
    if result['status'] == 'passed' and master.steps:
        result.update(status='failed', error={'code': 'unused_mock_steps', 'message': 'script has unconsumed exchanges'})
    shutil.copyfile(scenario_path, output / 'scenario.json')
    shutil.copyfile(profile_path, output / 'sample-profile.json')
    profile, _ = load_profile(profile_path)
    shutil.copyfile(PROJECT / profile['sources']['ldf']['project_copy'], output / 'LIN.ldf')
    (output / 'bus.jsonl').write_text(''.join(json.dumps(e, ensure_ascii=False, allow_nan=False) + '\n'
                                           for e in result.pop('journal')), encoding='utf-8')
    result.update(scope='mock_only', sent_to_hardware=False, physical_validation_status='not_evaluated',
                  started_at=started_at, completed_at=now(), remaining_mock_steps=len(master.steps),
                  device_calls=master.calls,
                  input_and_log_sha256={name: sha256(output / name)
                                       for name in ('scenario.json', 'sample-profile.json', 'LIN.ldf', 'bus.jsonl')},
                  code_sha256={f'src/typhoon_lab/{name}': sha256(Path(__file__).with_name(name))
                               for name in ('lin_session.py', 'lin_transport.py', 'tle9877.py')})
    write_json(output / 'session.json', result)
    return {**result, 'output_dir': str(output),
            'files': [str(output / name) for name in ('session.json', 'bus.jsonl', 'scenario.json', 'sample-profile.json', 'LIN.ldf')]}
