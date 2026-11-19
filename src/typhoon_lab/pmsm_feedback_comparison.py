"""Single-mechanism comparisons with identical sensing and controller paths."""
from .analysis import load_waveforms
from .config import number
from .pmsm_current_fault import PMSMCurrentFeedbackAdapter as Current
from .pmsm_fault import PMSMFeedbackAdapter as Speed
from .pmsm_preview import PERIOD, PMSMPreviewAdapter, analyze_preview, write_preview_report

SCOPE = '软件模型速度与q轴电流双路径采集；单一偏置或零偏置对照。'


class PMSMComparisonAdapter(PMSMPreviewAdapter):
    model_id = 'pmsm_feedback_comparison'
    source_model_id = 'pmsm_software_preview'
    signals = Speed.signals + Current.signals[len(PMSMPreviewAdapter.signals):]
    columns = Speed.columns + Current.columns[len(PMSMPreviewAdapter.columns):]
    units = {**Speed.units, **Current.units}
    changes = Speed.changes + [Current.changes[-1]]
    fixed_fields = {
        **Speed.fixed_fields, 'fault.bias_a': Current.fixed_fields['fault.bias_a'],
        'fault.kind': {'type': 'string', 'enum': ['feedback_comparison'],
                       'setting_stage': 'model_copy_before_compile'},
    }
    conditional_constraints = PMSMPreviewAdapter.conditional_constraints + ['at_most_one_nonzero_bias']

    def validate(self, raw, sweep=False):
        base = dict(raw)
        f = base.pop('fault', None)
        c = super().validate(base, sweep)
        if (not isinstance(f, dict) or set(f) != {'kind', 'at_s', 'bias_a', 'bias_rpm'} or
                f['kind'] != 'feedback_comparison'):
            raise ValueError('explicit comparison time and both bias values required')
        at = number(f['at_s'], 'fault.at_s', .2, c['capture']['duration_s'] - .2)
        rpm = number(f['bias_rpm'], 'fault.bias_rpm', 0, 300)
        amps = number(f['bias_a'], 'fault.bias_a', -5, 5)
        if abs(at / PERIOD - round(at / PERIOD)) > 1e-7 or (rpm and amps):
            raise ValueError('comparison requires an on-grid time and at most one active bias')
        c['fault'] = dict(kind=f['kind'], at_s=at, bias_a=amps, bias_rpm=rpm)
        return c

    def prepare(self, api, c):
        result = super().prepare(api, c)
        result['feedback_injection'] = Speed.install_bias(api, c)
        result['current_feedback_injection'] = Current.install_bias(api, c)
        result['scope'] = SCOPE
        return result

    def analyze(self, path, c):
        result = analyze_preview(path, c, self.columns)
        data = load_waveforms(path, ('t_relative_s', 't_simulation_s', *self.columns))
        speed = Speed.observe_bias(data, c)
        current = Current.observe_bias(data, c)
        result['fault_observation'] = {
            'speed': speed, 'current': current,
            'observed_at_s': speed['observed_at_s'] or current['observed_at_s'],
            'injection_verified': speed['injection_verified'] and current['injection_verified'],
        }
        result['checks'].update(speed['checks'], **current['checks'])
        result['status'] = 'passed' if all(result['checks'].values()) else 'failed'
        result['scope'] = SCOPE
        return result

    def report(self, path, manifest):
        return write_preview_report(path, manifest, self.columns, SCOPE)
