"""Declared field-file readers. No devices, inferred clocks, or sample repair."""
import csv
import codecs
import json
import math
import re
from pathlib import Path

from .external_waveforms import relative_file
from .tle9877 import decode_frame_from_ldf, pid

TIME_UNITS = {'s': 1., 'ms': 1e-3, 'us': 1e-6, 'ns': 1e-9}
UNITS = {'V': ('V', 1.), 'mV': ('V', .001), 'A': ('A', 1.), 'mA': ('A', .001),
         'rpm': ('rpm', 1.), 'RPM': ('rpm', 1.), 'rad/s': ('rpm', 30 / math.pi), 'Nm': ('Nm', 1.),
         '1': ('1', 1.), 'degC': ('degC', 1.)}
KINDS = {'physical', 'virtual_hil', 'mock', 'synthetic', 'unconfirmed'}
SPEED_ROLES = {'requested_speed', 'encoded_speed', 'board_target_speed', 'board_speed', 'model_speed'}
ROLES = SPEED_ROLES | {'gate', 'feedback_voltage', 'current', 'model_response', 'other'}
LIN_ROLES = {'ControlSetspeed': 'encoded_speed', 'Setspeed': 'board_target_speed',
             'ActualSpeed': 'board_speed', 'Current': 'current'}


def read_json(path):
    def invalid(value):
        raise ValueError(f'nonfinite JSON constant: {value}')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=invalid)


def number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be finite')
    return float(value)


def window(value, name):
    if value is None:
        return
    if not isinstance(value, list) or len(value) != 2 or number(value[0], name) >= number(value[1], name):
        raise ValueError(f'{name} needs increasing endpoints')


def metadata(value, name, allowed=None):
    if not isinstance(value, dict) or set(value) != {'value', 'status', 'source'}:
        raise ValueError(f'{name} needs value/status/source')
    if value['status'] not in {'confirmed', 'inferred', 'unconfirmed'} or not isinstance(value['source'], str):
        raise ValueError(f'invalid {name} metadata')
    if value['status'] != 'unconfirmed' and (value['value'] is None or not value['source'].strip()):
        raise ValueError(f'{name} requires evidence')
    if allowed is not None and value['value'] is not None and value['value'] not in allowed:
        raise ValueError(f'unsupported {name}: {value["value"]}')


def confirmed(value):
    return value.get('value') if value.get('status') == 'confirmed' else None


def _identifier(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError(f'{name} must be letters/digits/underscore/hyphen')


def validate_intake(data):
    allowed = {'schema_version', 'dataset_id', 'purpose', 'ldf', 'sources', 'events', 'criteria', 'references'}
    if not isinstance(data, dict) or set(data) - allowed or type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('field intake requires schema_version=1 and documented fields')
    for name in ('dataset_id', 'purpose'):
        if not isinstance(data.get(name), str) or not data[name].strip():
            raise ValueError(f'intake needs {name}')
    if data.get('ldf') is not None:
        relative_file(Path.cwd(), data['ldf'])
    if not isinstance(data.get('sources'), list) or not data['sources']:
        raise ValueError('sources must be nonempty')
    if any(not isinstance(data.get(key, []), list) for key in ('events', 'criteria')):
        raise ValueError('events and criteria must be lists')
    ids = set()
    for source in data['sources']:
        if not isinstance(source, dict) or set(source) - {'id', 'file', 'format', 'encoding', 'delimiter', 'skip_rows',
                'source_kind', 'provenance', 'device', 'metadata', 'time', 'alignment', 'signals', 'columns', 'detail_window_s'}:
            raise ValueError('unsupported source fields')
        sid = source.get('id')
        _identifier(sid, 'source.id')
        if sid in ids:
            raise ValueError('duplicate source id')
        ids.add(sid)
        relative_file(Path.cwd(), source.get('file'))
        if source.get('format') not in {'waveform_csv', 'lin_jsonl', 'lin_csv'} or source.get('source_kind') not in KINDS:
            raise ValueError('unsupported source format or kind')
        metadata(source.get('provenance'), sid + '.provenance')
        if not isinstance(source.get('device'), (dict, str)):
            raise ValueError('source needs device identification (unknown values may be null)')
        if not isinstance(source.get('encoding', 'utf-8-sig'), str):
            raise ValueError('encoding must be explicit text')
        codecs.lookup(source.get('encoding', 'utf-8-sig'))
        if source.get('delimiter', ',') not in {',', ';', '\t'}:
            raise ValueError('unsupported CSV delimiter')
        if type(source.get('skip_rows', 0)) is not int or source.get('skip_rows', 0) < 0:
            raise ValueError('skip_rows must be a nonnegative integer')
        time = source.get('time', {})
        if not isinstance(time, dict) or set(time) - {'field', 'unit', 'clock_domain', 'max_gap_s'}:
            raise ValueError('unsupported time fields')
        if not isinstance(time.get('field'), str) or not time['field'] or not isinstance(time.get('clock_domain'), str) or not time['clock_domain']:
            raise ValueError('time needs field and clock_domain')
        metadata(time.get('unit'), sid + '.time.unit', TIME_UNITS)
        if source['format'] == 'lin_jsonl' and time['field'] not in {'session_time_s', 'raw.device_time_s'}:
            raise ValueError('lin_jsonl time.field must be session_time_s or raw.device_time_s')
        if time.get('max_gap_s') is not None and number(time['max_gap_s'], 'max_gap_s') <= 0:
            raise ValueError('max_gap_s must be positive')
        alignment = source.get('alignment')
        if alignment is not None:
            if not isinstance(alignment, dict) or set(alignment) != {'group', 'scale', 'offset_s', 'uncertainty_s', 'valid_range_s', 'basis'}:
                raise ValueError('alignment needs group/scale/offset_s/uncertainty_s/valid_range_s/basis')
            _identifier(alignment['group'], 'alignment.group')
            if number(alignment['scale'], 'scale') <= 0 or number(alignment['uncertainty_s'], 'uncertainty_s') < 0:
                raise ValueError('invalid alignment scale or uncertainty')
            number(alignment['offset_s'], 'offset_s')
            window(alignment['valid_range_s'], 'valid_range_s')
            if alignment['valid_range_s'] is None or not isinstance(alignment['basis'], str) or not alignment['basis'].strip():
                raise ValueError('alignment needs validity range and evidence')
        window(source.get('detail_window_s'), 'detail_window_s')
        if source['format'] == 'waveform_csv':
            signals = source.get('signals')
            if not isinstance(signals, list) or not signals:
                raise ValueError('waveform_csv needs signals')
            names = set()
            for signal in signals:
                if not isinstance(signal, dict) or set(signal) - {'id', 'column', 'role', 'unit', 'scale', 'offset', 'conversion_basis', 'measurement_point'}:
                    raise ValueError('unsupported signal fields')
                _identifier(signal.get('id'), 'signal.id')
                if signal['id'] in names or not isinstance(signal.get('column'), str) or signal.get('role') not in ROLES:
                    raise ValueError('invalid signal id/column/role')
                names.add(signal['id'])
                metadata(signal.get('unit'), 'signal.unit', UNITS)
                scale, offset = number(signal.get('scale', 1), 'scale'), number(signal.get('offset', 0), 'offset')
                if (scale != 1 or offset != 0) and not signal.get('conversion_basis'):
                    raise ValueError('explicit scaling/offset needs conversion_basis')
        elif source['format'] == 'lin_csv':
            columns = source.get('columns', {})
            if set(columns) != {'direction', 'identifier', 'identifier_kind', 'data', 'checksum', 'driver_status'} or not all(isinstance(v, str) and v for v in columns.values()):
                raise ValueError('lin_csv needs all documented column mappings')
    event_ids = set()
    for event in data.get('events', []):
        if not isinstance(event, dict) or set(event) != {'id', 'label', 'source_id', 'time_s', 'confirmed', 'basis'}:
            raise ValueError('events need id/label/source_id/time_s/confirmed/basis')
        _identifier(event['id'], 'event.id')
        if event['id'] in event_ids or event['source_id'] not in ids or type(event['confirmed']) is not bool:
            raise ValueError('invalid event identity/source/confirmation')
        event_ids.add(event['id'])
        if event['time_s'] is not None:
            number(event['time_s'], 'event.time_s')
        if not isinstance(event['basis'], str) or (event['confirmed'] and (not event['basis'].strip() or event['time_s'] is None)):
            raise ValueError('confirmed events need time and basis')
    criterion_ids = set()
    for item in data.get('criteria', []):
        common = {'id', 'type', 'signal', 'window_s', 'confirmed', 'basis', 'max_gap_s', 'min_samples'}
        specific = {'speed_tracking': {'target_rpm', 'max_error_rpm'}, 'max_current': {'limit_a'},
                    'stop': {'event_id', 'threshold_rpm', 'deadline_s', 'hold_s', 'max_time_uncertainty_s'}}
        if not isinstance(item, dict) or item.get('type') not in specific or set(item) - common - specific[item['type']]:
            raise ValueError('unsupported criterion')
        _identifier(item.get('id'), 'criterion.id')
        if item['id'] in criterion_ids or type(item.get('confirmed')) is not bool or not isinstance(item.get('basis'), str):
            raise ValueError('invalid criterion identity/confirmation/basis')
        criterion_ids.add(item['id'])
        if item.get('signal') is not None and (not isinstance(item['signal'], str) or item['signal'].split('.')[0] not in ids or item['signal'].count('.') != 1):
            raise ValueError('criterion signal must be source.signal')
        window(item.get('window_s'), 'criterion.window_s')
        if type(item.get('min_samples', 3)) is not int or item.get('min_samples', 3) < 2:
            raise ValueError('min_samples must be >=2')
        for key in specific[item['type']] | {'max_gap_s'}:
            value = item.get(key)
            if key == 'event_id':
                if value is not None and value not in event_ids:
                    raise ValueError('unknown stop event')
            elif value is not None:
                n = number(value, key)
                if key != 'target_rpm' and (n < 0 or (key in {'max_gap_s', 'deadline_s', 'hold_s'} and n == 0)):
                    raise ValueError(f'invalid {key}')
    return data


def _numeric(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _nested(value, key):
    for part in key.split('.'):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def aligned_time(source, t):
    a = source.get('alignment')
    if t is None or not a or not a['valid_range_s'][0] <= t <= a['valid_range_s'][1]:
        return None
    mapped = a['scale'] * t + a['offset_s']
    return mapped if math.isfinite(mapped) else None


def _csv_rows(path, source):
    with Path(path).open(encoding=source.get('encoding', 'utf-8-sig'), newline='') as f:
        for _ in range(source.get('skip_rows', 0)):
            next(f, None)
        reader = csv.DictReader(f, delimiter=source.get('delimiter', ','))
        headers = reader.fieldnames or []
        if not headers or len(set(headers)) != len(headers) or any(not h for h in headers):
            raise ValueError('missing or duplicate CSV header')
        required = {source['time']['field']}
        required.update(s['column'] for s in source.get('signals', []))
        required.update(source.get('columns', {}).values())
        if not required <= set(headers):
            raise ValueError(f'missing columns: {sorted(required - set(headers))}')
        rows = list(reader)
        if any(None in row for row in rows):
            raise ValueError('CSV row has more values than its header')
        return rows


def read_source(path, source, ldf):
    """Preserve row order and nulls; issues never silently remove source samples."""
    result = {'id': source['id'], 'source_kind': source['source_kind'], 'clock_domain': source['time']['clock_domain'],
              'alignment': source.get('alignment'), 'issues': [], 'time_raw': [], 'time_s': [],
              'aligned_time_s': [], 'signals': {}, 'frames': [], 'journal': []}
    issues = result['issues']
    try:
        if source['format'] == 'lin_jsonl':
            rows = []
            with Path(path).open(encoding=source.get('encoding', 'utf-8-sig')) as f:
                for line, text in enumerate(f, 1):
                    try:
                        row = json.loads(text, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
                        if not isinstance(row, dict):
                            raise ValueError('journal row must be an object')
                        result['journal'].append(row)
                        if row.get('event') == 'exchange':
                            rows.append(row)
                    except ValueError as exc:
                        issues.append({'row': line, 'code': 'invalid_json', 'message': str(exc)})
        else:
            rows = _csv_rows(path, source)
        if source['format'] == 'waveform_csv':
            for s in source['signals']:
                unit = confirmed(s['unit'])
                result['signals'][s['id']] = {'role': s['role'], 'unit': UNITS[unit][0] if unit else None,
                    'unit_metadata': s['unit'], 'values_raw': [], 'values': []}
        time_unit = confirmed(source['time']['unit'])
        previous = None
        for index, row in enumerate(rows):
            raw_time = _numeric(_nested(row, source['time']['field']) if source['format'] == 'lin_jsonl' else row.get(source['time']['field']))
            t = raw_time * TIME_UNITS[time_unit] if raw_time is not None and time_unit else None
            if source['format'] == 'lin_jsonl':
                domain = _nested(row, 'raw.clock_domain') if source['time']['field'] == 'raw.device_time_s' else row.get('host_clock_domain')
                if domain is not None and domain != source['time']['clock_domain']:
                    issues.append({'row': index, 'code': 'clock_domain_mismatch', 'recorded': domain})
                    t = None
            result['time_raw'].append(raw_time)
            result['time_s'].append(t)
            result['aligned_time_s'].append(aligned_time(source, t))
            if raw_time is None:
                issues.append({'row': index, 'code': 'missing_or_invalid_time'})
            elif previous is not None and (raw_time < previous or (raw_time == previous and source['format'] == 'waveform_csv')):
                issues.append({'row': index, 'code': 'time_not_monotonic'})
            if raw_time is not None:
                previous = raw_time
            if source['format'] == 'waveform_csv':
                if None in row or any(v is None for v in row.values()):
                    issues.append({'row': index, 'code': 'column_count_mismatch'})
                for s in source['signals']:
                    signal = result['signals'][s['id']]
                    raw = _numeric(row.get(s['column']))
                    signal['values_raw'].append(raw)
                    unit = confirmed(s['unit'])
                    value = (raw * s.get('scale', 1) + s.get('offset', 0)) * UNITS[unit][1] if raw is not None and unit else None
                    if value is not None and not math.isfinite(value):
                        issues.append({'row': index, 'code': 'conversion_overflow', 'signal': s['id']})
                        value = None
                    signal['values'].append(value)
                    if raw is None:
                        issues.append({'row': index, 'code': 'missing_or_invalid_value', 'signal': s['id']})
            else:
                frame = read_frame(row, source, ldf)
                result['frames'].append(frame)
                if frame['status'] == 'failed':
                    issues.append({'row': index, 'code': 'invalid_lin_frame', 'message': frame['error']})
                for signal in result['signals'].values():
                    signal['values'].append(None)
                    signal['values_raw'].append(None)
                if frame.get('decoded'):
                    for name, item in frame['decoded']['signals'].items():
                        if item['unit'] not in UNITS:
                            continue
                        if name not in result['signals']:
                            result['signals'][name] = {'role': LIN_ROLES.get(name, 'other'),
                                'unit': UNITS[item['unit']][0], 'unit_metadata': {'value': item['unit'], 'status': 'confirmed', 'source': 'packaged LDF'},
                                'values_raw': [None] * (index + 1), 'values': [None] * (index + 1)}
                        signal = result['signals'][name]
                        signal['values_raw'][-1] = item['raw']
                        if item['validity'] == 'valid' and frame['status'] == 'passed':
                            signal['values'][-1] = item['value'] * UNITS[item['unit']][1]
        if not rows:
            issues.append({'code': 'no_samples'})
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, csv.Error) as exc:
        message = f'{type(exc).__name__}: {source["file"]}' if isinstance(exc, OSError) else str(exc)
        issues.append({'code': 'source_read_error', 'message': message})
    times = [t for t in result['time_s'] if t is not None]
    intervals = [b - a for a, b in zip(result['time_s'], result['time_s'][1:]) if a is not None and b is not None and b > a]
    max_gap = source['time'].get('max_gap_s')
    result['timing'] = {'samples': len(result['time_raw']), 'range_s': [min(times), max(times)] if times else None,
        'min_interval_s': min(intervals) if intervals else None, 'max_interval_s': max(intervals) if intervals else None,
        'gaps': sum(dt > max_gap + 1e-12 for dt in intervals) if max_gap else None}
    if max_gap and result['timing']['gaps']:
        issues.append({'code': 'sampling_gap', 'count': result['timing']['gaps']})
    result['data_quality_status'] = 'failed' if issues else 'passed'
    return result


def read_frame(row, source, ldf):
    """Unknown and damaged frames remain inspectable; derived values stay null."""
    if source['format'] == 'lin_jsonl':
        raw = row.get('raw') or {}
        identifier, kind = raw.get('pid'), 'pid'
        data, checksum = raw.get('data'), raw.get('checksum')
        status = raw.get('driver_status')
        direction = {'publish': 'tx', 'request': 'rx'}.get(row.get('operation'))
        if row.get('status') not in (None, 'passed'):
            status = 'exchange_failed'
    else:
        col = source['columns']
        raw = dict(row)
        identifier, kind = row.get(col['identifier']), row.get(col['identifier_kind'])
        data, checksum = row.get(col['data']), row.get(col['checksum'])
        status, direction = row.get(col['driver_status']), row.get(col['direction'])
    result = {'raw': raw, 'direction': direction, 'status': 'failed', 'decoded': None,
              'meaning': 'local_tx_record' if direction == 'tx' else 'response_record', 'error': None}
    try:
        if isinstance(identifier, str):
            identifier = int(identifier, 0)
        if isinstance(checksum, str):
            checksum = int(checksum, 0) if checksum.strip() else None
        if type(identifier) is not int or kind not in {'id', 'pid'} or not 0 <= identifier <= (63 if kind == 'id' else 255):
            raise ValueError('invalid identifier/kind; use decimal or 0x-prefixed hexadecimal integers')
        if direction not in {'tx', 'rx'} or status != 'ok':
            raise ValueError('missing/failed direction or driver status')
        frame_id = identifier & 63
        if kind == 'pid' and identifier != pid(frame_id):
            raise ValueError('PID parity mismatch')
        frame = next((f['name'] for f in ldf['frames'] if f['frame_id'] == frame_id), None)
        if frame is None:
            result.update(status='unsupported', error='frame is outside supplied business LDF')
            return result
        decoded = decode_frame_from_ldf(ldf, frame, data, identifier=identifier, identifier_kind=kind, received_checksum=checksum)
        result.update(decoded=decoded, status='passed' if checksum is not None else 'unverified',
                      error=None if checksum is not None else 'checksum not supplied')
    except (ValueError, TypeError, KeyError) as exc:
        result['error'] = str(exc)
    return result
