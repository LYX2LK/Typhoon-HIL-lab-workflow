"""HzWatt steady-state comparison against installed official tabulated references."""
from pathlib import Path
import numpy as np
from .analysis import load_waveforms
from .adapters.pv import PVAdapter,REFERENCE_POINTS

def analyze_pv(path,config):
    config=PVAdapter().validate(config)
    d=load_waveforms(Path(path),('t_relative_s','t_simulation_s',*PVAdapter.columns))
    t=np.asarray(d['t_simulation_s']);rel=np.asarray(d['t_relative_s'])
    dt=float(np.median(np.diff(t)));n=len(t);rate=1/dt
    cap=config['capture'];a=config['acceptance'];fpu=config['parameters']['frequency_pu']
    if n<a['min_samples'] or abs(n*dt-cap['duration_s'])>dt+1e-8 or abs(rate/cap['sample_rate_hz']-1)>.001:
        raise ValueError('PV capture length/rate does not match configuration')
    if t[0]+1e-8<cap['settle_s']: raise ValueError('PV capture begins before declared settling interval')
    if abs(rel[0])>dt+1e-8 or not np.allclose(np.diff(rel),np.diff(t),rtol=1e-5,atol=1e-8):
        raise ValueError('PV relative and simulation time axes disagree')
    power=np.asarray(d['ActivePower_kW']);reference=np.asarray(d['PowerReference_kW'])
    freq=np.asarray(d['Frequency_Hz']);enable=np.asarray(d['Enable']);alarm=np.asarray(d['AlarmCode'])
    target_kw=250.*REFERENCE_POINTS[fpu];target_hz=50.*fpu
    # Wrong excitation or unavailable feedback invalidates performance evaluation.
    frequency_error=float(np.max(np.abs(freq-target_hz)))
    if frequency_error>a['max_frequency_error_hz']+1e-12: raise ValueError('observed grid frequency differs from declared excitation')
    if not np.allclose(enable,1.,rtol=0,atol=1e-6): raise ValueError('PV enable feedback is not active throughout capture')
    error=np.abs(power-target_kw)/abs(target_kw);referror=np.abs(reference-250.)/250.
    limit=a['max_relative_power_error'];exceeded=error>limit+1e-12
    checks=[{'name':'active_power_all_samples','passed':not bool(np.any(exceeded)),'observed':float(error.max()),'limit':limit},
            {'name':'curtailment_reference_all_samples','passed':bool(np.all(referror<=limit+1e-12)),'observed':float(referror.max()),'limit':limit},
            {'name':'no_alarm','passed':bool(np.all(np.abs(alarm)<=1e-6)),'observed_max_absolute_code':float(np.max(np.abs(alarm))),'limit':0.}]
    return {'schema_version':1,'model':config['model'],'backend':config['backend'],
            'status':'passed' if all(c['passed'] for c in checks) else 'failed',
            'capture':{'sample_count':n,'sample_rate_hz':rate,'duration_s':n*dt,'first_simulation_time_s':float(t[0]),'last_simulation_time_s':float(t[-1])},
            'power':{'expected_kw':target_kw,'expected_pu':REFERENCE_POINTS[fpu],'mean_kw':float(power.mean()),
                     'min_kw':float(power.min()),'max_kw':float(power.max()),'max_relative_error':float(error.max()),
                     'exceeded_sample_count':int(exceeded.sum())},
            'control_evidence':{'frequency_target_hz':target_hz,'frequency_mean_hz':float(freq.mean()),
                                'max_frequency_error_hz':frequency_error,'reference_mean_kw':float(reference.mean()),'reference_expected_kw':250.,
                                'reference_meaning':'Pcurtailment times nominal power before HzWatt adjustment',
                                'enable_range':[float(enable.min()),float(enable.max())],'alarm_range':[float(alarm.min()),float(alarm.max())]},
            'reactive_power':{'mean_kvar':float(np.mean(d['ReactivePower_kVAr']))},
            'checks':checks,
            'analysis':{'window':'all captured samples after configured settling interval','evaluation_sample_count':n,
                        'formula':'max(abs(ActivePower_kW - 250*reference_pu)/(250*reference_pu))',
                        'reference_signal_check':'Pref_fb_kW = Pcurtailment(1 pu)*250 kW; confirmed in generated model C signal path',
                        'reference_kind':'installed official HzWatt reference table; independent startup teaching adaptation',
                        'reference_points':{'0.985':1.2,'0.996':1.,'1.0':1.,'1.02':.68},
                        'filtering':'none','interpolation':'none','missing_values':'error',
                        'scope':'two steady-state operating points; no dynamic event or hardware compliance claim'}}
