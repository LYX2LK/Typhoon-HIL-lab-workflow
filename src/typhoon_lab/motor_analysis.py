"""Deterministic startup tracking metrics; incomplete evidence is an error."""
import math
from pathlib import Path
from statistics import median
import numpy as np
from .analysis import load_waveforms

COLUMNS = ('t_relative_s', 't_simulation_s', 'Speed_rpm', 'ElectromagneticTorque_Nm', 'SpeedReference_rpm', 'LoadCommand_Nm')


def analyze_motor(path, config):
    if config['events']:
        return analyze_motor_step(path, config)
    d = load_waveforms(Path(path), COLUMNS)
    t = np.asarray(d['t_simulation_s']); rel = np.asarray(d['t_relative_s'])
    step = float(median(np.diff(t))); rate = 1/step; n = len(t)
    a, cap, p = config['acceptance'], config['capture'], config['parameters']
    if n < a['min_samples'] or rate + 1e-6 < a['min_sample_rate_hz']:
        raise ValueError('insufficient motor samples or time resolution; performance was not evaluated')
    if abs(rate/cap['sample_rate_hz']-1) > .01 or abs(n*step-cap['duration_s']) > step+1e-9:
        raise ValueError('motor capture length/rate does not match declared acquisition')
    start, end = a['window_start_s'], a['window_end_s']
    if t[0] > start+step+1e-9 or t[-1]+step < end-1e-9:
        raise ValueError('motor evaluation window is incomplete')
    if t[0] > step+1e-9 or rel[0] > step+1e-9:
        raise ValueError('motor startup capture did not begin at simulation startup')
    reference = p['reference_speed_rpm']
    if reference == 0:
        raise ValueError('relative speed error requires nonzero reference')
    if not np.allclose(d['SpeedReference_rpm'], reference, rtol=0, atol=1e-6):
        raise ValueError('observed speed reference differs from configuration')
    if not np.allclose(d['LoadCommand_Nm'], 4*p['load_pu'], rtol=0, atol=1e-6):
        raise ValueError('observed torque load command differs from configuration')
    mask = (t >= start) & (t < end)
    indices = np.flatnonzero(mask)
    if len(indices) < max(2, math.floor((end-start)*rate)-1):
        raise ValueError('insufficient samples inside the motor evaluation window')
    speed = np.asarray(d['Speed_rpm'])[mask]; torque = np.asarray(d['ElectromagneticTorque_Nm'])[mask]
    absolute = np.abs(speed-reference); relative = absolute/abs(reference)
    limit = a['max_relative_speed_error']
    # Small floating-point boundary slack is far below the measurement resolution.
    exceeded = relative > limit+1e-12
    times = t[mask][exceeded].tolist()
    passed = not bool(np.any(exceeded))
    maximum = float(np.max(relative))
    return {'schema_version':2, 'model':config['model'], 'backend':config['backend'], 'status':'passed' if passed else 'failed',
            'capture':{'sample_count':n,'sample_rate_hz':rate,'duration_s':n*step,
                       'first_simulation_time_s':float(t[0]),'last_simulation_time_s':float(t[-1])},
            'speed':{'reference_rpm':reference,'mean_rpm':float(np.mean(speed)),
                     'max_absolute_error_rpm':float(np.max(absolute)),'max_relative_error':maximum,
                     'exceeded_sample_count':len(times),'exceeded_times_s':times,
                     'worst_error_time_s':float(t[mask][int(np.argmax(relative))])},
            'electromagnetic_torque':{'mean_nm':float(np.mean(torque)),'min_nm':float(np.min(torque)),'max_nm':float(np.max(torque))},
            'control_evidence':{'speed_reference_min_rpm':min(d['SpeedReference_rpm']), 'speed_reference_max_rpm':max(d['SpeedReference_rpm']),
                                'load_command_min_nm':min(d['LoadCommand_Nm']), 'load_command_max_nm':max(d['LoadCommand_Nm'])},
            'checks':[{'name':'speed_tracking_all_samples','passed':passed,'observed':maximum,'expected':0.,'limit':limit}],
            'analysis':{'window_s':[start,end],'window_semantics':'start <= simulation time < end','evaluation_sample_count':len(indices),
                        'formula':'max(abs(Speed_rpm-reference_rpm)/abs(reference_rpm))',
                        'reference_kind':'project teaching criterion adapted from installed test_indm_speed_check; independent startup, lower capture rate',
                        'filtering':'none','interpolation':'none','missing_values':'error; no performance evaluation',
                        'endpoint_coverage_tolerance_s':step}}


def analyze_motor_step(path, config):
    from .adapters.induction import CONTROL_PERIOD_S, InductionMotorAdapter
    config = InductionMotorAdapter().validate(config)
    d = load_waveforms(Path(path), COLUMNS)
    t = np.asarray(d['t_simulation_s'])
    rel = np.asarray(d['t_relative_s'])
    speed = np.asarray(d['Speed_rpm'])
    reference = np.asarray(d['SpeedReference_rpm'])
    torque = np.asarray(d['ElectromagneticTorque_Nm'])
    load = np.asarray(d['LoadCommand_Nm'])
    sample_s = float(median(np.diff(t)))
    rate = 1/sample_s
    count = len(t)
    a, cap, p = config['acceptance'], config['capture'], config['parameters']
    if count < a['min_samples'] or rate + 1e-6 < a['min_sample_rate_hz']:
        raise ValueError('insufficient motor samples or time resolution; performance was not evaluated')
    if abs(rate/cap['sample_rate_hz']-1) > .01 or abs(count*sample_s-cap['duration_s']) > sample_s+1e-9:
        raise ValueError('motor capture length/rate does not match declared acquisition')
    if t[0] > sample_s+1e-9 or rel[0] > sample_s+1e-9 or t[-1]+sample_s < a['window_end_s']-1e-9:
        raise ValueError('motor step capture does not cover startup and the final evaluation window')
    expected_load = 4*p['load_pu']
    if not np.allclose(load, expected_load, rtol=0, atol=1e-6):
        raise ValueError('observed torque load command differs from configuration')

    event = config['events'][0]
    initial, final = p['reference_speed_rpm'], event['value']
    scheduled = event['at_s']
    direction = 1 if final > initial else -1
    level_tolerance_rpm = 1e-3
    ready = 2*max(CONTROL_PERIOD_S, sample_s)
    candidates = np.flatnonzero((t >= ready) &
                                (direction*(reference-initial) >= abs(final-initial)/2))
    changed_index = int(candidates[0]) if len(candidates) else None
    observed = float(t[changed_index]) if changed_index is not None else None
    interval = [float(t[changed_index-1]), observed] if changed_index is not None and changed_index > 0 else None
    timing = (observed is not None and scheduled-sample_s-1e-9 <= observed <=
              scheduled+CONTROL_PERIOD_S+sample_s+1e-9)
    before = reference[(t >= ready) & (t < (observed if observed is not None else scheduled))]
    after = reference[changed_index:] if changed_index is not None else np.asarray([])
    levels = (len(before) > 0 and len(after) > 0 and
              bool(np.all(np.abs(before-initial) <= level_tolerance_rpm)) and
              bool(np.all(np.abs(after-final) <= level_tolerance_rpm)))
    event_valid = observed is not None and timing and levels
    event_record = {**event, 'requested_at_s': scheduled, 'scheduled_at_s': scheduled,
                    'mechanism': 'model_step', 'model_step_trigger_at_s': scheduled,
                    'pipeline_compensation_s': 0, 'signal_column': 'SpeedReference_rpm',
                    'expected_before_rpm': initial, 'expected_after_rpm': final,
                    'observed_at_s': observed, 'observed_interval_s': interval,
                    'time_resolution_s': sample_s,
                    'observed_before_range_rpm': [float(np.min(before)), float(np.max(before))] if len(before) else None,
                    'observed_after_range_rpm': [float(np.min(after)), float(np.max(after))] if len(after) else None,
                    'status': 'passed' if event_valid else 'error'}

    def window_indices(start, end):
        indices = np.flatnonzero((t >= start-1e-9) & (t < end-1e-9))
        if len(indices) < max(2, math.floor((end-start)*rate)-1):
            raise ValueError('motor step evaluation window is incomplete')
        return indices

    pre_start = scheduled-a['pre_event_window_s']
    pre = window_indices(pre_start, scheduled)
    pre_errors = np.abs(speed[pre]-initial)/abs(initial)
    pre_max = float(np.max(pre_errors))
    limit = a['max_relative_speed_error']
    pre_passed = pre_max <= limit+1e-12
    final_start = max(a['window_start_s'], observed+a['post_event_delay_s']) if observed is not None else None
    final_indices = window_indices(final_start, a['window_end_s']) if event_valid else np.asarray([], dtype=int)
    final_errors = np.abs(speed[final_indices]-final)/abs(final) if len(final_indices) else np.asarray([])
    exceeded = final_errors > limit+1e-12
    final_max = float(np.max(final_errors)) if len(final_errors) else None
    final_passed = bool(len(final_errors)) and not bool(np.any(exceeded))
    exceeded_times = t[final_indices][exceeded].tolist() if len(final_indices) else []

    settling = None
    overshoot = None
    if event_valid:
        tail = np.flatnonzero(t >= observed-1e-9)
        tail_errors = np.abs(speed[tail]-final)/abs(final)
        bad = np.flatnonzero(tail_errors > limit+1e-12)
        settled_at = int(tail[bad[-1]+1]) if len(bad) and bad[-1]+1 < len(tail) else (int(tail[0]) if not len(bad) else None)
        if settled_at is not None:
            settling = max(0.0, float(t[settled_at]-observed))
        overshoot = max(0.0, float(np.max(direction*(speed[tail]-final))))/abs(final-initial)
    settling_passed = settling is not None and settling <= a['post_event_delay_s']+sample_s+1e-9
    checks = [
        {'name': 'event_observed', 'kind': 'event', 'passed': observed is not None, 'observed': observed, 'expected': scheduled},
        {'name': 'event_timing', 'kind': 'event', 'passed': timing, 'observed': observed, 'expected': scheduled, 'limit_s': CONTROL_PERIOD_S+sample_s},
        {'name': 'event_levels', 'kind': 'event', 'passed': levels, 'observed': event_record['observed_after_range_rpm'], 'expected': final, 'limit_rpm': level_tolerance_rpm},
        {'name': 'pre_event_tracking', 'kind': 'performance', 'passed': pre_passed, 'observed': pre_max, 'expected': 0, 'limit': limit},
        {'name': 'post_event_tracking', 'kind': 'performance', 'passed': final_passed, 'observed': final_max, 'expected': 0, 'limit': limit},
        {'name': 'settling_time', 'kind': 'performance', 'passed': settling_passed, 'observed': settling, 'expected': 0, 'limit_s': a['post_event_delay_s']},
    ]
    status = 'error' if not event_valid else ('passed' if all(x['passed'] for x in checks) else 'failed')
    return {'schema_version': 2, 'model': config['model'], 'backend': config['backend'], 'status': status,
            'capture': {'sample_count': count, 'sample_rate_hz': rate, 'duration_s': count*sample_s,
                        'first_simulation_time_s': float(t[0]), 'last_simulation_time_s': float(t[-1])},
            'events': [event_record],
            'speed': {'initial_reference_rpm': initial, 'final_reference_rpm': final,
                      'pre_event_max_relative_error': pre_max,
                      'post_event_mean_rpm': float(np.mean(speed[final_indices])) if len(final_indices) else None,
                      'post_event_max_relative_error': final_max,
                      'post_event_exceeded_sample_count': len(exceeded_times),
                      'post_event_exceeded_times_s': exceeded_times,
                      'settling_time_s': settling, 'directional_overshoot_fraction_of_step': overshoot},
            'electromagnetic_torque': {'min_nm': float(np.min(torque)), 'max_nm': float(np.max(torque)),
                                       'pre_event_mean_nm': float(np.mean(torque[pre])),
                                       'post_event_mean_nm': float(np.mean(torque[final_indices])) if len(final_indices) else None},
            'control_evidence': {'speed_reference_min_rpm': float(np.min(reference)),
                                 'speed_reference_max_rpm': float(np.max(reference)),
                                 'load_command_min_nm': float(np.min(load)),
                                 'load_command_max_nm': float(np.max(load))},
            'checks': checks,
            'analysis': {'pre_event_window_s': [pre_start, scheduled],
                         'post_event_window_s': [final_start, a['window_end_s']] if final_start is not None else None,
                         'post_event_delay_from_observed_s': a['post_event_delay_s'],
                         'evaluation_sample_count': len(final_indices),
                         'settling_definition': 'first sample inside final target +/- 1% with all remaining samples inside until capture end',
                         'overshoot_definition': 'excess beyond final target in step direction divided by absolute reference step; descriptive only',
                         'reference_kind': 'project teaching criterion adapted from installed test_indm_speed_check; not an IEC or GB/T product limit',
                         'filtering': 'none', 'interpolation': 'none', 'missing_values': 'error; no performance evaluation'}}
