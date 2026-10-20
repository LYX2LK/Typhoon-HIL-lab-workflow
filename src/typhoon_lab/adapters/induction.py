"""Induction machine startup tracking, mapped by the local 2026.3 preflight."""
from copy import deepcopy
from pathlib import Path
import math
import re
from ..config import number

CONTROL_PERIOD_S = 100e-6


class InductionMotorAdapter:
    model_id = 'induction_motor_closed_loop'
    schema_version = 2
    has_events = True
    capture_before_start = True
    sources = ('Vgrid',)
    signals = ('Speed', 'Torque', 'LabSpeedReference', 'LabLoadCommand')
    columns = ('Speed_rpm', 'ElectromagneticTorque_Nm', 'SpeedReference_rpm', 'LoadCommand_Nm')
    units = dict(zip(columns, ('rpm', 'N m', 'rpm', 'N m')))
    changes = ['Add LabSpeedReference and LabLoadCommand in the run copy; for a speed event, insert LabSpeedStep and LabSpeedSum before rpm_to_w_elec. Preserve the official plant and controller.']

    def validate(self, raw, sweep=False):
        if sweep:
            raise ValueError('motor cases use independent run configurations; sweep remains RLC-only')
        c = deepcopy(raw)
        keys = {'schema_version', 'model', 'backend', 'parameters', 'events', 'capture', 'acceptance'}
        if not isinstance(c, dict) or set(c) != keys:
            raise ValueError(f'motor configuration keys must be exactly {sorted(keys)}')
        if type(c['schema_version']) is not int or c['schema_version'] != 2 or c['model'] != self.model_id or c['backend'] != 'virtual_hil':
            raise ValueError('motor requires its registered model, schema_version 2 and virtual_hil')
        if not isinstance(c['events'], list) or len(c['events']) > 1:
            raise ValueError('motor events must contain zero or one speed-reference step')
        dynamic = bool(c['events'])
        rules = {
            'parameters': {'grid_phase_rms_v': (1, 1000), 'grid_frequency_hz': (1, 100),
                           'grid_phase_deg': (-360, 360), 'reference_speed_rpm': (200, 1700), 'load_pu': (0, 1)},
            'capture': {'start_s': (0, 0), 'duration_s': (.02, 5), 'sample_rate_hz': (10000, 200000), 'wall_timeout_s': (10, 300)},
            'acceptance': {'window_start_s': (0, 5), 'window_end_s': (.001, 5),
                           'max_relative_speed_error': (.0001, .2), 'min_sample_rate_hz': (10000, 200000), 'min_samples': (256, 100000)},
        }
        if dynamic:
            rules['acceptance'].update(pre_event_window_s=(.01, 2), post_event_delay_s=(.1, 4))
        for group, fields in rules.items():
            if not isinstance(c[group], dict) or set(c[group]) != set(fields):
                raise ValueError(f'{group} keys must be exactly {sorted(fields)}')
            for key, bounds in fields.items():
                c[group][key] = number(c[group][key], f'{group}.{key}', *bounds)
        a, cap = c['acceptance'], c['capture']
        if not a['min_samples'].is_integer():
            raise ValueError('min_samples must be an integer')
        a['min_samples'] = int(a['min_samples'])
        n = cap['duration_s'] * cap['sample_rate_hz']
        if not a['min_samples'] <= n <= 100000 or cap['sample_rate_hz'] < a['min_sample_rate_hz']:
            raise ValueError('capture exceeds sample limits or falls below the minimum rate')
        if not 0 <= a['window_start_s'] < a['window_end_s'] <= cap['duration_s']:
            raise ValueError('capture must include the complete evaluation window')
        if a['window_end_s'] - a['window_start_s'] < 10 / a['min_sample_rate_hz']:
            raise ValueError('evaluation window is too short for the minimum resolution')
        if dynamic:
            event = c['events'][0]
            if not isinstance(event, dict) or set(event) != {'at_s', 'target', 'value'}:
                raise ValueError('motor event requires at_s, target and value')
            if event['target'] != 'reference_speed_rpm':
                raise ValueError('motor event target must be reference_speed_rpm')
            event['at_s'] = number(event['at_s'], 'events.at_s', .02, cap['duration_s'])
            event['value'] = number(event['value'], 'events.value', 200, 1700)
            if event['value'] == c['parameters']['reference_speed_rpm']:
                raise ValueError('motor event must change the speed reference')
            ticks = event['at_s'] / CONTROL_PERIOD_S
            if not math.isclose(ticks, round(ticks), rel_tol=0, abs_tol=1e-7):
                raise ValueError('motor event time must align to the 100 us control period')
            if event['at_s'] < a['pre_event_window_s'] or a['window_start_s'] < event['at_s'] + a['post_event_delay_s'] - 1e-10:
                raise ValueError('motor capture must contain the pre-event and delayed post-event windows')
            if a['window_end_s'] - a['window_start_s'] < .1:
                raise ValueError('motor post-event evaluation window must last at least 0.1 s')
        return c

    def inspect_parameters(self, api):
        required = ('Speed RPM', 'Enable', 'IM_Load', 'Load_sel', 'Mux', 'Gain6', 'To rpm', 'rpm_to_w_elec', 'Vgrid', 'machine 3')
        for name in required:
            if api.get_item(name) is None:
                raise ValueError(f'motor component missing: {name}')
        text = Path(api.get_model_file_path()).read_text(encoding='utf-8')
        period = re.findall(r'(?m)^\s*Ts\s*=\s*([+\-0-9.eE]+)\s*$', text)
        if len(period) != 1:
            raise ValueError('expected one literal Ts initialization assignment')
        machine = api.get_property_values(api.get_item('machine 3'))
        def scalar_gain(name):
            value = api.get_property_values(api.get_item(name))['gain']
            # Schematic API 2026.3 resolves scalar Gain properties as [value].
            if isinstance(value, (list, tuple)):
                if len(value) != 1:
                    raise ValueError(f'{name} must have a scalar gain')
                value = value[0]
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f'{name} gain must be finite')
            return value
        return {'control_period_s': float(period[0]),
                'load_gain_nm_per_pu': scalar_gain('Gain6'),
                'speed_conversion': scalar_gain('To rpm'),
                'machine': {k: machine[k] for k in ('load_src', 'ext_mdl_load_type', 'el_trq_out', 'mech_speed_out', 'Jm', 'pms')},
                'load_selector': 1, 'load_mode': 'constant IM_Load; selector 0 gives zero load',
                'units_basis': 'Speed follows mechanical angular speed through 60/(2*np.pi); Torque follows machine electromagnetic torque output T; Gain6 feeds the machine torque load input.'}

    def prepare(self, api, config):
        values = self.inspect_parameters(api)
        if not math.isclose(values['control_period_s'], CONTROL_PERIOD_S, abs_tol=1e-12) or not math.isclose(values['load_gain_nm_per_pu'], 4, abs_tol=1e-12):
            raise ValueError('motor timing or load scaling differs from the verified mapping')
        if not math.isclose(values['speed_conversion'], 60/(2*math.pi), abs_tol=1e-12):
            raise ValueError('motor speed conversion differs from the verified rpm mapping')
        if values['machine']['load_src'] != 'Model' or values['machine']['ext_mdl_load_type'] != 'torque' or values['machine']['el_trq_out'] is not True or values['machine']['mech_speed_out'] is not True:
            raise ValueError('motor mechanical interface differs from the verified mapping')
        applied_reference = api.get_item('Speed RPM')
        if config['events']:
            event = config['events'][0]
            converter = api.get_item('rpm_to_w_elec')
            connections = api.find_connections(api.term(applied_reference, 'out'), api.term(converter, 'in'))
            if len(connections) != 1:
                raise ValueError('expected exactly one Speed RPM -> rpm_to_w_elec connection')
            api.delete_item(connections[0])
            step = api.create_component('core/Step', name='LabSpeedStep', position=(2960, 920))
            adder = api.create_component('core/Sum', name='LabSpeedSum', position=(3100, 920))
            api.set_property_values(step, {'step_time': str(event['at_s']), 'initial_value': '0',
                                           'final_value': str(event['value']-config['parameters']['reference_speed_rpm']),
                                           'execution_rate': 'Ts'})
            api.set_property_values(adder, {'signs': '++', 'execution_rate': 'Ts'})
            api.create_connection(api.term(applied_reference, 'out'), api.term(adder, 'in'))
            api.create_connection(api.term(step, 'out'), api.term(adder, 'in1'))
            api.create_connection(api.term(adder, 'out'), api.term(converter, 'in'))
            readback = api.get_property_values(step)
            for key, expected in (('step_time', event['at_s']), ('initial_value', 0),
                                  ('final_value', event['value']-config['parameters']['reference_speed_rpm'])):
                value = readback[key]
                value = value[0] if isinstance(value, (list, tuple)) else value
                if not math.isclose(float(value), expected, rel_tol=0, abs_tol=1e-9):
                    raise ValueError(f'motor Step readback mismatch: {key}')
            values['speed_step'] = {'trigger_at_s': event['at_s'], 'properties_read_back': readback}
            applied_reference = adder
        for name, source in (('LabSpeedReference', applied_reference), ('LabLoadCommand', api.get_item('Gain6'))):
            probe = api.create_component('core/Probe', name=name, position=(3200, 1000))
            api.create_connection(api.term(source, 'out'), api.term(probe, 'in'))
        return values

    def initialize(self, hil, config):
        from ..runtime import require
        p = config['parameters']
        require(hil.set_source_sine_waveform('Vgrid', rms=p['grid_phase_rms_v'], frequency=p['grid_frequency_hz'], phase=p['grid_phase_deg']), 'set motor three phase source')
        source = hil.get_source_settings('Vgrid')
        for key, expected in (('rms', p['grid_phase_rms_v']), ('frequency', p['grid_frequency_hz']), ('phase', p['grid_phase_deg'])):
            if not source or not math.isclose(float(source[key]), expected, abs_tol=1e-8):
                raise ValueError(f'motor source readback mismatch: {key}')
        requested = {'Load_sel': 1., 'IM_Load': p['load_pu'], 'Speed RPM': p['reference_speed_rpm'], 'Enable': 1.}
        for name, value in requested.items():
            require(hil.set_scada_input_value(name, value), f'set motor {name}')
        actual = {name: hil.get_scada_input_settings(name) for name in requested}
        for name, value in requested.items():
            if not actual[name] or not math.isclose(float(actual[name]['input_value']), value, abs_tol=1e-8):
                raise ValueError(f'motor SCADA readback mismatch: {name}')
        return {'actual_source_settings': source, 'requested_scada_settings': requested,
                'actual_scada_settings': actual, 'load_torque_command_nm': 4*p['load_pu']}

    def schedule(self, hil, config):
        return self.describe_schedule(config)

    def describe_schedule(self, config):
        return [{**event, 'scheduled_at_s': event['at_s'], 'mechanism': 'model_step',
                 'model_step_trigger_at_s': event['at_s'], 'pipeline_compensation_s': 0}
                for event in config['events']]

    def record_events(self, config):
        return bool(config['events'])

    def check_sampling(self, rate, count, config):
        if rate < config['acceptance']['min_sample_rate_hz'] or count < config['acceptance']['min_samples']:
            raise ValueError('actual motor sampling is below the declared minimum')
        if abs(rate/config['capture']['sample_rate_hz']-1) > .01 or abs(count/rate-config['capture']['duration_s']) > 1/rate+1e-10:
            raise ValueError('actual motor capture cannot provide the requested time resolution/window')

    def analyze(self, path, config):
        from ..motor_analysis import analyze_motor
        return analyze_motor(path, config)

    def report(self, path, manifest):
        from ..motor_reporting import write_motor_report
        return write_motor_report(path, manifest)
