"""Bounded numerical queries over anonymous observation files, without evaluator data."""
import csv
import math
from pathlib import Path
import re

import numpy as np

UNITS = {'model_speed_rpm': 'rpm', 'controller_speed_rpm': 'rpm', 'reference_speed_rpm': 'rpm',
         'load_nm': 'Nm', 'torque_nm': 'Nm', 'ia_a': 'A', 'ib_a': 'A', 'ic_a': 'A'}
CATALOG = {
    'statistics': {'arguments': {'channels': '开放通道名数组', 'window_s': '[开始,结束]'},
                   'returns': 'statistics.<通道>.mean/min/max/rms/peak_to_peak，单位随通道'},
    'difference': {'arguments': {'left': '开放通道', 'right': '同单位开放通道', 'window_s': '[开始,结束]'},
                   'returns': 'mean_difference/min_difference/max_difference/max_abs_difference；差值为left-right'},
    'events': {'arguments': {'channel': 'reference_speed_rpm或load_nm', 'window_s': '[开始,结束]'},
               'returns': 'count及changes数组，只报告实际记录的指令变化'},
    'availability': {'arguments': {'channels': '需核对的信号名称数组'}, 'returns': '每项是否已记录'},
    'controller_knowledge': {'arguments': {}, 'returns': '模型控制关系、40A指令限幅的含义及状态观测缺口'},
}
CONTROL_KNOWLEDGE = {
    'speed_loop': '速度给定减控制器使用的速度反馈进入速度调节器；模型速度为独立观测。',
    'current_command_limit_a': 40,
    'limit_location': 'speed_regulation.Limit1对电流幅值指令is_ref限幅，随后进入MTPA电流指令生成。',
    'phase_current_peak_is_command_limit_indicator': False,
    'reason': '相电流瞬时峰值与限幅前后电流指令不是同一信号，峰值超过40A不能单独证明指令限幅生效。',
    'unrecorded': ['current_command_before_limit', 'current_command_after_limit', 'current_limit_flag', 'speed_pi_integrator'],
    'diagnostic_scope': '可报告测点间偏差及相容机制；唯一根因仍取决于其他候选机制与可区分观测。',
}


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('finite numeric value required')
    return float(value)


def load_observations(path):
    with Path(path).open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ['time_s', *UNITS]:
            raise ValueError('unexpected anonymous observation columns')
        rows = list(reader)
    if len(rows) < 10:
        raise ValueError('insufficient observations')
    data = {k: np.array([float(row[k]) for row in rows]) for k in reader.fieldnames}
    if any(not np.all(np.isfinite(v)) for v in data.values()) or np.any(np.diff(data['time_s']) <= 0):
        raise ValueError('invalid observations or time grid')
    step=float(np.median(np.diff(data['time_s'])))
    if np.max(np.abs(np.diff(data['time_s'])-step))>max(1e-10,step*1e-4):
        raise ValueError('nonuniform observation time grid')
    return data


class ObservationTools:
    """Only this object is used by model-selected queries; it never loads private.json."""
    def __init__(self, data, available, *, units=None, knowledge=None, event_channels=None, event_thresholds=None):
        self.data = data
        self.units = UNITS if units is None else units
        self.knowledge = CONTROL_KNOWLEDGE if knowledge is None else knowledge
        self.event_channels = ('reference_speed_rpm', 'load_nm') if event_channels is None else event_channels
        self.event_thresholds = {'reference_speed_rpm': 1, 'load_nm': 1e-7} if event_thresholds is None else event_thresholds
        self.available = set(available)
        if not self.available <= set(self.units):
            raise ValueError('unknown public channels')

    def window(self, args):
        window = args['window_s']
        if not isinstance(window, list) or len(window) != 2:
            raise ValueError('window_s requires two numbers')
        start, end = map(number, window)
        t = self.data['time_s']
        step = float(np.median(np.diff(t)))
        if not t[0] <= start < end <= t[-1] + step + 1e-10:
            raise ValueError('window outside available recording')
        mask = (t >= start) & (t < end)
        if np.count_nonzero(mask) < 5:
            raise ValueError('window contains fewer than five samples')
        return mask

    def execute(self, name, args):
        try:
            if name not in CATALOG or not isinstance(args, dict):
                raise ValueError('unknown tool or invalid arguments')
            expected = set(CATALOG[name]['arguments'])
            if set(args) != expected:
                raise ValueError('tool argument fields differ')
            if name == 'controller_knowledge':
                return {'status': 'ok', **self.knowledge}
            channels = args.get('channels', [args['left'], args['right']] if name == 'difference' else [args.get('channel')])
            if not isinstance(channels, list) or not 1 <= len(channels) <= max(8, len(self.units)) or any(
                    not isinstance(c, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', c) for c in channels):
                raise ValueError('invalid channel names')
            if name == 'availability':
                return {'status': 'ok', 'available': {c: c in self.available for c in channels}}
            missing = [c for c in channels if c not in self.available]
            if missing:
                return {'status': 'unavailable', 'channels': missing,
                        'meaning': '未开放或未记录，不能作为测得的零值或排除机制的证据。'}
            mask = self.window(args)
            result = {'status': 'ok', 'window_s': args['window_s'], 'sample_count': int(np.count_nonzero(mask))}
            if name == 'statistics':
                values = {}
                for channel in channels:
                    x = self.data[channel][mask]
                    values[channel] = {'mean': float(np.mean(x)), 'min': float(np.min(x)), 'max': float(np.max(x)),
                                       'rms': float(np.sqrt(np.mean(x*x))), 'peak_to_peak': float(np.ptp(x)), 'unit': self.units[channel]}
                result['statistics'] = values
            elif name == 'difference':
                left, right = args['left'], args['right']
                if self.units[left] != self.units[right]:
                    raise ValueError('difference requires matching units')
                x = (self.data[left] - self.data[right])[mask]
                result.update(mean_difference=float(np.mean(x)), min_difference=float(np.min(x)),
                              max_difference=float(np.max(x)), max_abs_difference=float(np.max(np.abs(x))),
                              unit=self.units[left], definition='left minus right')
            else:
                channel = channels[0]
                if channel not in self.event_channels:
                    raise ValueError('events only supports recorded reference/load commands')
                t, x = self.data['time_s'], self.data[channel]
                threshold = self.event_thresholds[channel]
                ids = np.flatnonzero((np.abs(np.diff(x)) > threshold) & mask[1:]) + 1
                if len(ids) > 20:
                    raise ValueError('more than twenty command changes in window')
                result.update(count=len(ids), changes=[{'at_s': float(t[i]), 'before': float(x[i-1]), 'after': float(x[i])} for i in ids])
            return result
        except (KeyError, ValueError, TypeError) as exc:
            return {'status': 'invalid_query', 'reason': str(exc)}


def check_prediction(prediction, result):
    if result['status'] != 'ok' or prediction['metric'] is None:
        return {'status': 'not_assessable', 'reason': 'no available numeric observation for this prediction'}
    value = result
    try:
        for key in prediction['metric'].split('.'):
            value = value[key]
        value = number(value)
        low, high = prediction['expected_interval']
        return {'status': 'within' if low <= value <= high else 'outside', 'observed': value,
                'expected_interval': [low, high], 'hypothesis_id': prediction['hypothesis_id'], 'metric': prediction['metric']}
    except (KeyError, TypeError, ValueError):
        return {'status': 'not_assessable', 'reason': 'prediction metric not found in tool result'}
