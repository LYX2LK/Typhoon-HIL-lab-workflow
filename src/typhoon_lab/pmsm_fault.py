"""Model-side speed-feedback bias, with independently captured true/used speed."""
from copy import deepcopy
import math
from pathlib import Path
import numpy as np

from .analysis import load_waveforms
from .config import number
from .pmsm_preview import PMSMPreviewAdapter, PERIOD, analyze_preview, write_preview_report
from .utils import PROJECT

SCOPE = ('PMSM软件闭环速度反馈偏置核验；理想角度反馈与原电机参数假设保留。'
         '偏置注入模型内速度调节器实际使用的反馈路径，非实体传感器或固件故障验收。')


class PMSMFeedbackAdapter(PMSMPreviewAdapter):
    model_id = 'pmsm_feedback_probe'
    source_model_id = 'pmsm_software_preview'
    signals = PMSMPreviewAdapter.signals + ('LabSpeedFeedback', 'LabFeedbackBias')
    columns = PMSMPreviewAdapter.columns + ('SpeedFeedback_rad_s', 'FeedbackBias_rad_s')
    units = {**PMSMPreviewAdapter.units, 'SpeedFeedback_rad_s': 'rad/s', 'FeedbackBias_rad_s': 'rad/s'}
    changes = PMSMPreviewAdapter.changes + ['Add bias to Rate Transition1 output before speed_regulation.w; capture both sides and bias.']
    conditional_constraints = PMSMPreviewAdapter.conditional_constraints + ['feedback_bias_kind_time_and_magnitude_explicit']
    fixed_fields = {
        'fault.kind': {'type': 'string', 'enum': ['speed_feedback_bias'], 'setting_stage': 'model_copy_before_compile'},
        'fault.at_s': {'type': 'number', 'unit': 's', 'minimum': .2, 'maximum_ref': 'capture.duration_s - .2',
                       'quantum_s': PERIOD, 'setting_stage': 'model_copy_before_compile'},
        'fault.bias_rpm': {'type': 'number', 'unit': 'rpm', 'minimum': 0, 'maximum': 300,
                          'setting_stage': 'model_copy_before_compile', 'limit_source': 'software_prototype_scope'},
    }

    def validate(self, raw, sweep=False):
        c = deepcopy(raw)
        fault = c.pop('fault', None)
        c = super().validate(c, sweep)
        if not isinstance(fault, dict) or set(fault) != {'kind', 'at_s', 'bias_rpm'} or fault['kind'] != 'speed_feedback_bias':
            raise ValueError('explicit speed_feedback_bias definition required')
        fault['at_s'] = number(fault['at_s'], 'fault.at_s', .2, c['capture']['duration_s'] - .2)
        fault['bias_rpm'] = number(fault['bias_rpm'], 'fault.bias_rpm', 0, 300)
        if abs(fault['at_s'] / PERIOD - round(fault['at_s'] / PERIOD)) > 1e-7:
            raise ValueError('fault time must be on the control grid')
        c['fault'] = fault
        return c

    def prepare(self, api, c):
        result = super().prepare(api, c)
        result['feedback_injection'] = self.install_bias(api, c)
        result['scope'] = SCOPE
        return result

    @staticmethod
    def install_bias(api, c):
        source = api.term(api.get_item('Rate Transition1'), 'out')
        dest = api.term(api.get_item('speed_regulation'), 'w')
        connections = api.find_connections(source, dest)
        if len(connections) != 1:
            raise ValueError('speed-feedback source/destination differ from inspected model')
        api.delete_item(connections[0])
        bias = api.create_component('core/Step', name='LabBiasStep', position=(7800, 8300))
        adder = api.create_component('core/C function', name='LabFeedbackSum', position=(8000, 8300))
        props = {'step_time': str(c['fault']['at_s']), 'initial_value': '0',
                 'final_value': str(c['fault']['bias_rpm'] * math.pi / 30), 'execution_rate': 'Ts'}
        api.set_property_values(bias, props)
        # Persist explicit types/dimensions in component properties: transient terminal
        # overrides are regenerated when built-in Sum/Probe components compile.
        adder_properties = {'input_terminals': 'real in;real in1;',
                            'input_terminals_dimensions': '1;1', 'input_terminals_feedthrough': 'True;True',
                            'output_terminals': 'real out;', 'output_terminals_dimensions': '1',
                            'output_terminals_feedthrough': 'True', 'output_fnc': 'out = in + in1;',
                            'execution_rate': 'Ts'}
        api.set_property_values(adder, adder_properties)
        # C-function terminal declarations are materialized when the model loads.
        # Save/reload only the runtime copy, then reacquire all item handles.
        working = Path(api.get_model_file_path()).resolve()
        if not working.is_relative_to(PROJECT / 'results'):
            raise ValueError('feedback preparation requires a results-directory model copy')
        if api.save() is False or api.load(filename=str(working)) is not True:
            raise RuntimeError('cannot reload declared feedback terminals')
        source = api.term(api.get_item('Rate Transition1'), 'out')
        dest = api.term(api.get_item('speed_regulation'), 'w')
        bias = api.get_item('LabBiasStep')
        adder = api.get_item('LabFeedbackSum')
        api.create_connection(source, api.term(adder, 'in'))
        api.create_connection(api.term(bias, 'out'), api.term(adder, 'in1'))
        api.create_connection(api.term(adder, 'out'), dest)
        for i, (name, terminal) in enumerate((('LabSpeedFeedback', api.term(adder, 'out')),
                                             ('LabFeedbackBias', api.term(bias, 'out')))):
            probe = api.create_component('core/Probe', name=name, position=(8200 + i * 120, 8500))
            api.create_connection(terminal, api.term(probe, 'in'))
        for k, expected in props.items():
            actual = api.get_property_value(api.prop(bias, k))
            if k == 'execution_rate':
                valid = actual == expected
            else:
                if isinstance(actual, list) and len(actual) == 1:
                    actual = actual[0]
                valid = math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=1e-12)
            if not valid:
                raise ValueError('bias parameter readback mismatch: ' + k)
        return {'source': 'Rate Transition1.out', 'destination': 'speed_regulation.w',
                                        'fault': c['fault'], 'step_readback': api.get_property_values(bias),
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
        scale = 30 / math.pi
        before = np.asarray(d['MechanicalSpeed_rad_s']) * scale
        used = np.asarray(d['SpeedFeedback_rad_s']) * scale
        bias = np.asarray(d['FeedbackBias_rad_s']) * scale
        f = c['fault']
        pre = (t >= f['at_s'] - .05) & (t < f['at_s'] - 4 * PERIOD)
        post = (t >= f['at_s'] + .1) & (t < f['at_s'] + .2)
        if np.count_nonzero(pre) < 10 or np.count_nonzero(post) < 10:
            raise ValueError('missing injection observation windows')
        level = float(np.max(np.abs(bias[post] - f['bias_rpm'])))
        residual = float(np.max(np.abs((used - before)[post] - f['bias_rpm'])))
        hits = np.flatnonzero((t >= f['at_s'] - 1 / c['capture']['sample_rate_hz']) & (np.abs(bias) > .001))
        observed = float(t[hits[0]]) if len(hits) and f['bias_rpm'] else None
        timing = f['bias_rpm'] == 0 or (observed is not None and f['at_s'] - 1e-5 <= observed <= f['at_s'] + 4 * PERIOD + 1e-5)
        checks = {'bias_initial_zero': bool(np.max(np.abs(bias[pre])) <= .001),
                  'bias_post_level': level <= .001, 'bias_time': timing,
                  'feedback_steady_relation': residual <= 2.0}
        true_speed = np.asarray(d['MechanicalSpeed_rad_s']) * scale
        ref = np.asarray(d['Reference_rad_s']) * scale
        return {'requested': f, 'observed_at_s': observed, 'checks': checks,
            'post_window_s': [f['at_s'] + .1, f['at_s'] + .2], 'bias_level_error_rpm': level,
            'feedback_relation_max_error_rpm': residual, 'feedback_relation_tolerance_rpm': 2.0,
            'true_tracking_mean_error_rpm': float(np.mean((true_speed - ref)[post])),
            'used_feedback_mean_error_rpm': float(np.mean((used - ref)[post])),
            'injection_verified': all(checks.values())}

    def report(self, path, manifest):
        return write_preview_report(path, manifest, self.columns, SCOPE)
