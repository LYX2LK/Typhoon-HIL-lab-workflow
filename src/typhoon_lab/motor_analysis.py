"""Deterministic startup tracking metrics; incomplete evidence is an error."""
import math
from pathlib import Path
from statistics import median
import numpy as np
from .analysis import load_waveforms

COLUMNS = ('t_relative_s', 't_simulation_s', 'Speed_rpm', 'ElectromagneticTorque_Nm', 'SpeedReference_rpm', 'LoadCommand_Nm')


def analyze_motor(path, config):
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
