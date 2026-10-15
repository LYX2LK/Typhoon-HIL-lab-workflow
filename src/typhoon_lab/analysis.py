"""Deterministic RLC analysis. Never changes raw data or calls Typhoon."""
from __future__ import annotations
import cmath
import csv
import math
from pathlib import Path
from statistics import median

COLUMNS = ('t_relative_s', 't_simulation_s', 'I_A', 'Va1_V')
SIGNALS = (('I_A', 'A'), ('Va1_V', 'V'))


def _positive(value, name, allow_zero=False):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a finite number')
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be a finite number') from exc
    if not math.isfinite(value) or (value < 0 if allow_zero else value <= 0):
        raise ValueError(f'{name} must be finite and positive or permitted zero')
    return value


def load_waveforms(csv_path: Path) -> dict[str, list[float]]:
    """Reject invalid samples, gaps and misaligned time grids; no interpolation."""
    data = {name: [] for name in COLUMNS}
    with Path(csv_path).open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or set(reader.fieldnames) != set(COLUMNS):
            raise ValueError(f'CSV columns must be exactly {", ".join(COLUMNS)}')
        if len(reader.fieldnames) != len(COLUMNS):
            raise ValueError('CSV contains duplicate columns')
        for line, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f'Unexpected extra CSV values at line {line}')
            for name in COLUMNS:
                try:
                    value = float(row[name])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f'Invalid numeric value at line {line}, column {name}') from exc
                if not math.isfinite(value):
                    raise ValueError(f'Non-finite value at line {line}, column {name}')
                data[name].append(value)
    if len(data[COLUMNS[0]]) < 2:
        raise ValueError('At least two waveform samples are required')
    for name in COLUMNS[:2]:
        if any(b <= a for a, b in zip(data[name], data[name][1:])):
            raise ValueError(f'{name} must be strictly increasing')
    relative, simulation = data[COLUMNS[0]], data[COLUMNS[1]]
    if relative[0] < -1e-10 or simulation[0] < -1e-10:
        raise ValueError('Time coordinates must be nonnegative')
    step = median(b - a for a, b in zip(relative, relative[1:]))
    tolerance = max(1e-10, step * 1e-4)
    if any(abs(b - a - step) > tolerance for a, b in zip(relative, relative[1:])):
        raise ValueError('Waveform samples are not uniformly spaced; missing samples are not filled')
    origin = simulation[0] - relative[0]
    if any(abs(s - r - origin) > tolerance for r, s in zip(relative, simulation)):
        raise ValueError('Relative and simulation time coordinates do not share a time grid')
    return data


def expected_rlc_rms(config: dict) -> dict:
    """Steady sinusoidal phasor for Rin + [L || (R + C)]."""
    source, circuit = config['source'], config['circuit']
    vrms = _positive(source['rms_v'], 'source.rms_v')
    frequency = _positive(source['frequency_hz'], 'source.frequency_hz')
    phase = float(source.get('phase_deg', 0))
    if not math.isfinite(phase):
        raise ValueError('source.phase_deg must be finite')
    rin = _positive(circuit['rin_ohm'], 'circuit.rin_ohm')
    branch_r = _positive(circuit['branch_r_ohm'], 'circuit.branch_r_ohm', True)
    inductance = _positive(circuit['l_h'], 'circuit.l_h')
    capacitance = _positive(circuit['c_f'], 'circuit.c_f')
    omega = 2 * math.pi * frequency
    zl = complex(0, omega * inductance)
    zrc = branch_r + 1 / complex(0, omega * capacitance)
    if abs(zl + zrc) < 1e-15:
        raise ValueError('Ideal parallel resonance has no finite impedance reference')
    parallel = zl * zrc / (zl + zrc)
    total = rin + parallel
    current, voltage = vrms / total, vrms * parallel / total
    if not all(math.isfinite(value) for value in (abs(current), abs(voltage))):
        raise ValueError('The analytic RMS reference is non-finite')
    return {'I_A': abs(current), 'Va1_V': abs(voltage),
            'current_phase_deg': math.degrees(cmath.phase(current)) + phase,
            'voltage_phase_deg': math.degrees(cmath.phase(voltage)) + phase,
            'parallel_impedance_ohm': {'real': parallel.real, 'imaginary': parallel.imag},
            'input_impedance_ohm': {'real': total.real, 'imaginary': total.imag}}


def analyze(csv_path: Path, config: dict) -> dict:
    """Return deterministic JSON metrics; invalid data raises ValueError.

    A valid capture outside tolerance returns status='failed'.
    """
    reference = expected_rlc_rms(config)
    data = load_waveforms(Path(csv_path))
    count = len(data['t_relative_s'])
    acceptance = config.get('acceptance', {})
    minimum = acceptance.get('min_samples', 256)
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 2:
        raise ValueError('acceptance.min_samples must be an integer >= 2')
    if count < minimum:
        raise ValueError(f'Insufficient samples: {count}; required at least {minimum}')
    limit = _positive(acceptance.get('relative_rms_error', 0.03), 'acceptance.relative_rms_error', True)
    capture = config['capture']
    requested_rate = _positive(capture['sample_rate_hz'], 'capture.sample_rate_hz')
    requested_duration = _positive(capture['duration_s'], 'capture.duration_s')
    settle = _positive(capture.get('settle_s', 0), 'capture.settle_s', True)
    frequency = float(config['source']['frequency_hz'])
    times = data['t_relative_s']
    step = median(b - a for a, b in zip(times, times[1:]))
    rate, duration = 1 / step, times[-1] - times[0] + step
    rate_error = abs(rate - requested_rate) / requested_rate
    duration_error = abs(duration - requested_duration) / requested_duration
    checks = [
        {'name': 'sample_count', 'passed': count >= minimum, 'observed': count, 'expected': minimum, 'limit': minimum},
        {'name': 'sample_rate', 'passed': rate_error <= .01, 'observed': rate, 'expected': requested_rate, 'relative_error': rate_error, 'limit': .01},
        {'name': 'capture_duration', 'passed': duration_error <= max(.01, 1 / count), 'observed': duration, 'expected': requested_duration, 'relative_error': duration_error, 'limit': max(.01, 1 / count)},
        {'name': 'sampling_above_nyquist', 'passed': rate > 2 * frequency, 'observed': rate, 'expected': 2 * frequency, 'limit': 2 * frequency},
        {'name': 'settled_before_capture', 'passed': data['t_simulation_s'][0] + 1e-10 >= settle, 'observed': data['t_simulation_s'][0], 'expected': settle, 'limit': settle},
    ]
    signals = {}
    for name, unit in SIGNALS:
        try:
            rms = math.sqrt(math.fsum(value * value for value in data[name]) / count)
        except OverflowError as exc:
            raise ValueError(f'RMS overflow in {name}') from exc
        if not math.isfinite(rms):
            raise ValueError(f'Non-finite RMS in {name}')
        expected = reference[name]
        if expected <= 0:
            raise ValueError(f'Relative RMS error needs a nonzero reference for {name}')
        error = abs(rms - expected) / expected
        passed = error <= limit
        signals[name] = {'unit': unit, 'rms': rms, 'expected_rms': expected, 'relative_rms_error': error, 'passed': passed}
        checks.append({'name': f'{name}_rms', 'passed': passed, 'observed': rms, 'expected': expected, 'relative_error': error, 'limit': limit})
    cycles = duration * frequency
    warnings = []
    if abs(cycles - round(cycles)) > .005:
        warnings.append('Capture does not span an integer number of source cycles; finite-window RMS may differ from the steady sinusoidal reference.')
    return {'schema_version': 1, 'status': 'passed' if all(check['passed'] for check in checks) else 'failed',
            'model': config.get('model', 'rlc_filter'), 'backend': config.get('backend', 'virtual_hil'),
            'source_csv': Path(csv_path).name, 'sample_count': count, 'sample_rate_hz': rate,
            'capture': {'sample_count': count, 'sample_rate_hz': rate, 'span_s': times[-1] - times[0],
                        'duration_s': duration, 'cycles': cycles, 'first_simulation_time_s': data['t_simulation_s'][0],
                        'last_simulation_time_s': data['t_simulation_s'][-1]},
            'signals': signals, 'checks': checks,
            'reference': {'method': 'sinusoidal steady-state phasor',
                          'formula': 'Zp = (j*w*L)*(R + 1/(j*w*C))/(j*w*L + R + 1/(j*w*C)); I_rms = abs(V_rms/(Rin+Zp)); Va_rms = abs(V_rms*Zp/(Rin+Zp))',
                          'assumptions': ['linear ideal L and C', 'sinusoidal source', 'steady state', 'node branches are L and series R-C'], **reference},
            'analysis': {'rms_method': 'sqrt(sum(x*x)/N)', 'window': 'all raw captured samples',
                         'filtering': 'none', 'interpolation': 'none', 'missing_values': 'reject', 'warnings': warnings}}
