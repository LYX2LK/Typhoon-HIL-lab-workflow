"""Q-axis current feedback bias in the controller's actual input path."""
from copy import deepcopy
from pathlib import Path
import math
import numpy as np

from .analysis import load_waveforms
from .config import number
from .pmsm_preview import PMSMPreviewAdapter, PERIOD, analyze_preview, write_preview_report
from .utils import PROJECT

SCOPE = ('PMSM软件闭环q轴电流反馈偏置核验；在dq变换之后、电流调节器之前注入。'
         '保留独立dq电流与三相电流观测，理想角度反馈及原电机参数假设继续适用。')


class PMSMCurrentFeedbackAdapter(PMSMPreviewAdapter):
    model_id = 'pmsm_current_feedback_probe'
    source_model_id = 'pmsm_software_preview'
    signals = PMSMPreviewAdapter.signals + ('iq', 'LabIqFeedback', 'LabCurrentBias')
    columns = PMSMPreviewAdapter.columns + ('IqRaw_A', 'IqFeedback_A', 'CurrentBias_A')
    units = {**PMSMPreviewAdapter.units, 'IqRaw_A': 'A', 'IqFeedback_A': 'A', 'CurrentBias_A': 'A'}
    changes = PMSMPreviewAdapter.changes + ['Insert q-axis feedback bias between From15 and Current_regulation.iq.']
    fixed_fields = {
        'fault.kind': {'type': 'string', 'enum': ['q_current_feedback_bias'], 'setting_stage': 'model_copy_before_compile'},
        'fault.at_s': {'type': 'number', 'unit': 's', 'minimum': .2,
                       'maximum_ref': 'capture.duration_s - .2', 'quantum_s': PERIOD,
                       'setting_stage': 'model_copy_before_compile'},
        'fault.bias_a': {'type': 'number', 'unit': 'A', 'minimum': -5, 'maximum': 5,
                         'setting_stage': 'model_copy_before_compile', 'limit_source': 'software_prototype_scope'},
    }
    conditional_constraints = PMSMPreviewAdapter.conditional_constraints + ['explicit_q_current_feedback_fault']

    def validate(self, raw, sweep=False):
        c = deepcopy(raw)
        f = c.pop('fault', None)
        c = super().validate(c, sweep)
        if not isinstance(f, dict) or set(f) != {'kind', 'at_s', 'bias_a'} or f['kind'] != 'q_current_feedback_bias':
            raise ValueError('explicit q_current_feedback_bias definition required')
        f['at_s'] = number(f['at_s'], 'fault.at_s', .2, c['capture']['duration_s'] - .2)
        f['bias_a'] = number(f['bias_a'], 'fault.bias_a', -5, 5)
        if abs(f['at_s'] / PERIOD - round(f['at_s'] / PERIOD)) > 1e-7:
            raise ValueError('fault time must be on the control grid')
        c['fault'] = f
        return c

    def prepare(self, api, c):
        result = super().prepare(api, c)
        result['current_feedback_injection'] = self.install_bias(api, c)
        result['scope'] = SCOPE
        return result

    @staticmethod
    def install_bias(api, c):
        source = api.get_item('From15')
        dest = api.term(api.get_item('Current_regulation'), 'iq')
        connections = api.find_connections(source, dest)
        if len(connections) != 1:
            raise ValueError('inspected q-current feedback connection changed')
        api.delete_item(connections[0])
        step = api.create_component('core/Step', name='LabCurrentBiasStep', position=(8800, 8300))
        props = {'step_time': str(c['fault']['at_s']), 'initial_value': '0',
                 'final_value': str(c['fault']['bias_a']), 'execution_rate': 'Ts'}
        api.set_property_values(step, props)
        adder = api.create_component('core/C function', name='LabCurrentFeedbackSum', position=(9000, 8300))
        api.set_property_values(adder, {
            'input_terminals': 'real in;real in1;', 'input_terminals_dimensions': '1;1',
            'input_terminals_feedthrough': 'True;True', 'output_terminals': 'real out;',
            'output_terminals_dimensions': '1', 'output_terminals_feedthrough': 'True',
            'output_fnc': 'out = in + in1;', 'execution_rate': 'Ts'})
        working = Path(api.get_model_file_path()).resolve()
        if not working.is_relative_to(PROJECT / 'results'):
            raise ValueError('current fault preparation requires a results-directory model copy')
        if api.save() is False or api.load(filename=str(working)) is not True:
            raise RuntimeError('cannot reload declared current-feedback terminals')
        source = api.get_item('From15')
        dest = api.term(api.get_item('Current_regulation'), 'iq')
        step = api.get_item('LabCurrentBiasStep')
        adder = api.get_item('LabCurrentFeedbackSum')
        api.create_connection(source, api.term(adder, 'in'))
        api.create_connection(api.term(step, 'out'), api.term(adder, 'in1'))
        api.create_connection(api.term(adder, 'out'), dest)
        for i, (name, terminal) in enumerate((('LabIqFeedback', api.term(adder, 'out')),
                                             ('LabCurrentBias', api.term(step, 'out')))):
            probe = api.create_component('core/Probe', name=name, position=(9200 + 120*i, 8500))
            api.create_connection(terminal, api.term(probe, 'in'))
        for key, expected in props.items():
            actual = api.get_property_value(api.prop(step, key))
            if isinstance(actual, list) and len(actual) == 1:
                actual = actual[0]
            valid = actual == expected if key == 'execution_rate' else math.isclose(float(actual), float(expected), abs_tol=1e-9)
            if not valid:
                raise ValueError('current fault parameter readback mismatch: ' + key)
        if len(api.find_connections(api.term(adder, 'out'), dest)) != 1:
            raise ValueError('current feedback destination not connected')
        return {
            'source': 'From15 (I_abc_dq1.q_axis signal tag)', 'destination': 'Current_regulation.iq',
            'fault': c['fault'], 'step_readback': api.get_property_values(step),
            'adder_readback': api.get_property_values(adder)}

    def analyze(self, path, c):
        result = analyze_preview(path, c, self.columns)
        d = load_waveforms(path, ('t_relative_s', 't_simulation_s', *self.columns))
        observation = self.observe_bias(d, c)
        result['fault_observation'] = observation
        result['checks'].update(observation['checks'])
        result['status'] = 'passed' if all(result['checks'].values()) else 'failed'
        result['scope'] = SCOPE
        return result

    @staticmethod
    def observe_bias(d, c):
        t = np.asarray(d['t_simulation_s'])
        raw, used, bias = (np.asarray(d[k]) for k in ('IqRaw_A', 'IqFeedback_A', 'CurrentBias_A'))
        f = c['fault']
        pre = (t >= f['at_s'] - .05) & (t < f['at_s'] - 4*PERIOD)
        post = (t >= f['at_s'] + .1) & (t < f['at_s'] + .2)
        if min(np.count_nonzero(pre), np.count_nonzero(post)) < 10:
            raise ValueError('missing current injection windows')
        residual = (used - raw)[post] - f['bias_a']
        hit = np.flatnonzero((t >= f['at_s'] - 1/c['capture']['sample_rate_hz']) & (np.abs(bias) > .0001))
        observed = float(t[hit[0]]) if len(hit) and f['bias_a'] else None
        checks = {
            'current_bias_initial_zero': bool(np.max(np.abs(bias[pre])) <= .0001),
            'current_bias_post_level': bool(np.max(np.abs(bias[post] - f['bias_a'])) <= .0001),
            'current_bias_time': f['bias_a'] == 0 or (observed is not None and f['at_s'] - 1e-5 <= observed <= f['at_s'] + 4*PERIOD + 1e-5),
            'current_feedback_mean_relation': bool(abs(np.mean(residual)) <= .1),
            'current_feedback_rms_relation': bool(np.sqrt(np.mean(residual**2)) <= .5),
        }
        return {
            'requested': f, 'observed_at_s': observed, 'checks': checks,
            'post_window_s': [f['at_s'] + .1, f['at_s'] + .2],
            'feedback_relation_mean_error_a': float(np.mean(residual)),
            'feedback_relation_rms_error_a': float(np.sqrt(np.mean(residual**2))),
            'relation_tolerances_a': {'abs_mean': .1, 'rms': .5},
            'raw_iq_mean_a': float(np.mean(raw[post])), 'used_iq_mean_a': float(np.mean(used[post])),
            'injection_verified': all(checks.values())}

    def report(self, path, manifest):
        return write_preview_report(path, manifest, self.columns, SCOPE)
