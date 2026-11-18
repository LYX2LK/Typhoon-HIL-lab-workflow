"""Shared fixed PMSM recovery and response metrics; no simulator access."""
import csv
import math
import numpy as np


def recovery(t, error, onset, band=50., minimum_tail=.02):
    """Last band exit, observed return and finite-record censoring; no smoothing."""
    ids=np.flatnonzero(t>=onset)
    if len(ids)<2: raise ValueError('missing recovery window')
    bad=ids[np.abs(error[ids])>band]
    idx=int(bad[-1]+1) if len(bad) else int(ids[0])
    if idx>=len(t) or t[-1]-t[idx]<minimum_tail:
        return {'recovery_s':None,'recovery_interval_s':None,'recovery_censored':True,
                'observed_horizon_s':float(t[-1]-onset)}
    value=max(0.,float(t[idx]-onset))
    left=max(0.,float(t[idx-1]-onset)) if idx>0 else 0.
    return {'recovery_s':value,'recovery_interval_s':[left,value], 'recovery_censored':False,
            'observed_horizon_s':float(t[-1]-onset)}


def derive(d, metrics, config):
    t=np.asarray(d['t_simulation_s'])
    speed=np.asarray(d['MechanicalSpeed_rad_s'])*30/math.pi
    ref=np.asarray(d['Reference_rad_s'])*30/math.pi
    err=speed-ref
    events=metrics['events']
    if any(e['status']!='passed' or e['observed_at_s'] is None for e in events):
        raise ValueError('event application has not been established')
    first=min(e['observed_at_s'] for e in events) if events else .3
    last=max(e['observed_at_s'] for e in events) if events else .3
    window=(t>=first)&(t<first+.3)
    tail=(t>=last+.1)&(t<last+.3)
    if t[-1]<max(first+.3,last+.3)-2e-5: raise ValueError('incomplete analysis window')
    event_details=[]
    for e in events:
        i=int(np.searchsorted(t,e['observed_at_s']))
        event_details.append({**e,'detection_interval_s':[float(t[i-1]) if i else None,float(t[i])]})
    r=recovery(t,err,last)
    r.update(first_event_observed_s=first if events else None,last_event_observed_s=last if events else None,
             peak_abs_error_rpm=float(np.max(np.abs(err[window]))),
             peak_positive_error_rpm=float(np.max(err[window])),
             peak_negative_error_rpm=float(np.min(err[window])),
             iae_rpm_s=float(np.sum(np.diff(t[window])*(np.abs(err[window][1:])+np.abs(err[window][:-1]))/2)),
             minimum_speed_rpm=float(np.min(speed[window])),
             phase_current_peak_a=max(float(np.max(np.abs(np.asarray(d[k])[window]))) for k in ('Ia_A','Ib_A','Ic_A')),
             tail_error_peak_to_peak_rpm=float(np.ptp(err[tail])),
             settled_max_error_rpm=metrics['windows'][-1]['max_speed_error_rpm'],
             recovery_margin_ms=(.1-r['recovery_s'])*1000 if r['recovery_s'] is not None else None,
             events=event_details, sample_count=len(t))
    if not events:
        r.update(recovery_s=None,recovery_interval_s=None,recovery_censored=False,recovery_margin_ms=None)
    return r


def independent_check(path, result):
    """Separate stdlib loop/integration verifies key vectorized computations."""
    with path.open(encoding='utf-8') as f: rows=list(csv.DictReader(f))
    first=result['first_event_observed_s'] or .3
    last=result['last_event_observed_s'] or .3
    peak=0.;area=0.;previous=None;bad=None;raw=[]
    for row in rows:
        t=float(row['t_simulation_s'])
        e=(float(row['MechanicalSpeed_rad_s'])-float(row['Reference_rad_s']))*30/math.pi
        raw.append((t,e))
        if t>=last and abs(e)>50: bad=len(raw)-1
        if first<=t<first+.3:
            peak=max(peak,abs(e))
            if previous: area+=(t-previous[0])*(abs(e)+abs(previous[1]))/2
            previous=(t,e)
    idx=(bad+1) if bad is not None else next(i for i,(t,e) in enumerate(raw) if t>=last)
    rec=None if idx>=len(raw) or raw[-1][0]-raw[idx][0]<.02 else max(0.,raw[idx][0]-last)
    checks={'peak_error':math.isclose(peak,result['peak_abs_error_rpm'],abs_tol=1e-8),
            'iae':math.isclose(area,result['iae_rpm_s'],abs_tol=1e-8),
            'recovery':result['first_event_observed_s'] is None or rec==result['recovery_s']}
    if not all(checks.values()): raise ValueError(f'independent metric mismatch: {checks}')
    return checks


