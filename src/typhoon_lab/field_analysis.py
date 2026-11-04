"""Deterministic, sample-based checks on independently sourced field data."""
import math

from .field_intake import aligned_time, confirmed, read_source


def aggregate(states):
    return 'failed' if 'failed' in states else ('passed' if states and all(s == 'passed' for s in states) else 'not_evaluated')


def event_in_source(event, source, sources):
    if not event or not event['confirmed'] or event['time_s'] is None or not event['basis'].strip():
        return None, None, 'stop event is not confirmed'
    origin = sources[event['source_id']]
    if origin['id'] == source['id']:
        return event['time_s'], 0., None
    a, b = origin.get('alignment'), source.get('alignment')
    common = aligned_time(origin, event['time_s'])
    if not a or not b or a['group'] != b['group'] or common is None:
        return None, None, 'event and signal have no evidenced common clock'
    t = (common - b['offset_s']) / b['scale']
    if aligned_time(source, t) is None:
        return None, None, 'stop event is outside alignment validity'
    return t, (a['uncertainty_s'] + b['uncertainty_s']) / b['scale'], None


def evaluate(item, streams, sources, events):
    result = {'id': item['id'], 'type': item['type'], 'status': 'not_evaluated',
              'definition': item, 'reason': None, 'metrics': {}}

    def unavailable(reason):
        result['reason'] = reason
        return result

    fields = {'speed_tracking': ('target_rpm', 'max_error_rpm'), 'max_current': ('limit_a',),
              'stop': ('event_id', 'threshold_rpm', 'deadline_s', 'hold_s', 'max_time_uncertainty_s')}
    required = ('signal', 'window_s', 'max_gap_s') + fields[item['type']]
    if not item['confirmed'] or not item['basis'].strip() or any(item.get(k) is None for k in required):
        return unavailable('criterion, evidence, window or required parameters are not confirmed')
    sid, name = item['signal'].split('.')
    stream, source = streams[sid], sources[sid]
    signal = stream['signals'].get(name)
    if not signal:
        return unavailable('signal is missing from the supplied data')
    if stream['data_quality_status'] != 'passed':
        return unavailable('source has data-quality issues; inspect retained rows before judging')
    expected = 'A' if item['type'] == 'max_current' else 'rpm'
    roles = {'current'} if expected == 'A' else {'model_speed', 'board_speed'}
    if signal['unit'] != expected or signal['role'] not in roles or confirmed(source['time']['unit']) is None:
        return unavailable('confirmed time/value units and measured response role are required')
    start, end = item['window_s']
    max_gap = item['max_gap_s']
    pairs = [(t, y) for t, y in zip(stream['time_s'], signal['values']) if t is not None and y is not None]
    selected = [(t, y) for t, y in pairs if start - 1e-12 <= t <= end + 1e-12]
    if len(selected) < item.get('min_samples', 3):
        return unavailable('too few valid samples in the declared window')
    times, values = zip(*selected)
    if times[0] > start + max_gap + 1e-12 or times[-1] < end - max_gap - 1e-12 or any(b - a > max_gap + 1e-12 for a, b in zip(times, times[1:])):
        return unavailable('window coverage or sample gaps exceed max_gap_s')
    if any(b[0] - a[0] > max_gap + 1e-12 for a, b in zip(pairs, pairs[1:]) if a[0] < end and b[0] > start):
        return unavailable('a gap crossing a window boundary exceeds max_gap_s')
    result['metrics'].update(samples=len(times), observed_window_s=[times[0], times[-1]], maximum_gap_s=max(b-a for a,b in zip(times,times[1:])))
    if item['type'] == 'speed_tracking':
        measured = max(abs(y - item['target_rpm']) for y in values)
        if not math.isfinite(measured):
            return unavailable('speed-error calculation exceeds finite numerical range')
        result['metrics']['maximum_speed_error_rpm'] = measured
        passed = measured <= item['max_error_rpm'] + 1e-12
    elif item['type'] == 'max_current':
        measured = max(abs(y) for y in values)
        result['metrics']['maximum_absolute_current_a'] = measured
        passed = measured <= item['limit_a'] + 1e-12
    else:
        event = events.get(item['event_id'])
        if event and streams[event['source_id']]['data_quality_status'] != 'passed':
            return unavailable('stop-event source has data-quality issues')
        event_t, uncertainty, error = event_in_source(event, source, sources)
        if error:
            return unavailable(error)
        duration_scale = source['alignment']['scale'] if source.get('alignment') else 1.
        uncertainty *= duration_scale
        if uncertainty > item['max_time_uncertainty_s'] + 1e-12:
            return unavailable('clock uncertainty exceeds the allowed timing uncertainty')
        if source.get('alignment'):
            a = source['alignment']
            if start < a['valid_range_s'][0] or end > a['valid_range_s'][1]:
                return unavailable('evaluation window is outside alignment validity')
        required_end = event_t + (item['deadline_s'] + item['hold_s']) / duration_scale
        if start > event_t + 1e-12 or end + 1e-12 < required_end or times[-1] + 1e-12 < required_end:
            return unavailable('record must cover stop event, deadline and complete hold interval')
        result['metrics'].update(event_time_in_signal_clock_s=event_t, timing_uncertainty_s=uncertainty,
                                 duration_scale=duration_scale,
                                 definition='recorded samples below threshold for hold_s; no interpolation')
        candidate = None
        previous = event_t
        for t, y in selected:
            if t < event_t:
                previous = t
                continue
            if abs(y) <= item['threshold_rpm'] + 1e-12:
                if candidate is None:
                    candidate = (t, max(event_t, previous))
                if (t - candidate[0]) * duration_scale + 1e-12 >= item['hold_s']:
                    upper = (candidate[0] - event_t) * duration_scale + uncertainty
                    lower = max(0., (candidate[1] - event_t) * duration_scale - uncertainty)
                    result['metrics'].update(first_below_sample_s=candidate[0], hold_verified_until_s=t,
                                             response_interval_s=[lower, upper])
                    if lower <= item['deadline_s'] < upper - 1e-12:
                        return unavailable('sampling/clock interval straddles the stop deadline')
                    passed = upper <= item['deadline_s'] + 1e-12
                    break
            else:
                candidate = None
            previous = t
        else:
            passed = False
            result['metrics']['hold_found'] = False
    result.update(status='passed' if passed else 'failed', reason=None)
    return result


def analyze_data(root, intake, ldf):
    from .external_waveforms import relative_file
    streams = {s['id']: read_source(relative_file(root, s['file']), s, ldf) for s in intake['sources']}
    sources = {s['id']: s for s in intake['sources']}
    events = {e['id']: e for e in intake.get('events', [])}
    checks = [evaluate(item, streams, sources, events) for item in intake.get('criteria', [])]
    criteria_status = aggregate([c['status'] for c in checks])
    used = {c['signal'].split('.')[0] for c in intake.get('criteria', []) if c.get('signal')}
    for c in intake.get('criteria', []):
        if c.get('event_id') in events:
            used.add(events[c['event_id']]['source_id'])
    physical = bool(used) and all(sources[s]['source_kind'] == 'physical' and confirmed(sources[s]['provenance']) is not None for s in used)
    quality = 'failed' if any(s['data_quality_status'] == 'failed' for s in streams.values()) else 'passed'
    summaries = {}
    for sid, stream in streams.items():
        summaries[sid] = {}
        for name, signal in stream['signals'].items():
            values = [v for v in signal['values'] if v is not None]
            summaries[sid][name] = {'role': signal['role'], 'unit': signal['unit'], 'valid_samples': len(values),
                'missing_samples': len(signal['values']) - len(values),
                'minimum': min(values) if values else None, 'maximum': max(values) if values else None,
                'mean': math.fsum(v / len(values) for v in values) if values else None}
    incomplete = quality == 'failed' or any(confirmed(s['time']['unit']) is None for s in sources.values()) or any(
        x['unit'] is None for stream in streams.values() for x in stream['signals'].values())
    return {'schema_version': 1, 'dataset_id': intake['dataset_id'], 'data_quality_status': quality,
        'analysis_status': 'incomplete' if incomplete else 'completed', 'criteria_status': criteria_status,
        'performance_status': criteria_status if physical else 'not_evaluated',
        'performance_scope': 'only configured offline checks; sample origin is declared, not authenticated by file integrity',
        'status': 'failed' if quality == 'failed' or criteria_status == 'failed' else 'passed',
        'checks': checks, 'summaries': summaries, 'events': intake.get('events', []),
        'synchronization': {sid: {'clock_domain': s['time']['clock_domain'], 'alignment': s.get('alignment'),
            'status': 'declared_with_evidence' if s.get('alignment') else 'not_established'} for sid, s in sources.items()}}, streams
