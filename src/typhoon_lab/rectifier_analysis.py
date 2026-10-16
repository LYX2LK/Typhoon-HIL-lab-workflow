"""Independent ideal-diode bridge equations and deterministic raw-data analysis."""
from functools import lru_cache
import math
from pathlib import Path
from statistics import median
import numpy as np
from .analysis import load_waveforms

COLUMNS=("t_relative_s","t_simulation_s","Vdc_V","Iload_A","Icap_A")

@lru_cache(maxsize=32)
def bridge_reference(frequency,resistance,inductance,capacitance,steps_per_cycle=4000):
    """Integrate normalized peak input=1, using independent switched ODE + RK4.

    On: L di/dt=abs(sin(wt))-v; C dv/dt=i-v/R.
    Off: i=0, v(t+h)=v(t)*exp(-h/(R*C)). Current is projected to >=0
    at diode turn-off; this introduces <=one integration-step switching error.
    This is a numerical ideal-circuit reference, not measured Typhoon output.
    """
    if not (frequency>0 and resistance>0 and inductance>0 and capacitance>0): raise ValueError("positive reference parameters required")
    n=int(steps_per_cycle);h=1/(frequency*n)
    warm_cycles=math.ceil(max(1.,12*resistance*capacitance)*frequency)
    total=(warm_cycles+2)*n
    # Reuse phase values to avoid accumulated source phase error.
    sine=[abs(math.sin(2*math.pi*k/(2*n))) for k in range(2*n)]
    i=v=0.;last=[];previous=[]
    inv_l=1/inductance;inv_c=1/capacitance;inv_r=1/resistance
    decay=math.exp(-h/(resistance*capacitance))
    for k in range(total):
        if k>=total-n: last.append(v)
        elif k>=total-2*n: previous.append(v)
        p=(2*k)%(2*n);a=sine[p];b=sine[(p+1)%(2*n)];c=sine[(p+2)%(2*n)]
        if i<=0 and a<=v and b<=v*decay:
            i=0.;v*=decay
        else:
            di1=(a-v)*inv_l;dv1=(i-v*inv_r)*inv_c
            i2=i+h*.5*di1;v2=v+h*.5*dv1
            di2=(b-v2)*inv_l;dv2=(i2-v2*inv_r)*inv_c
            i3=i+h*.5*di2;v3=v+h*.5*dv2
            di3=(b-v3)*inv_l;dv3=(i3-v3*inv_r)*inv_c
            i4=i+h*di3;v4=v+h*dv3
            di4=(c-v4)*inv_l;dv4=(i4-v4*inv_r)*inv_c
            i=max(0.,i+h*(di1+2*di2+2*di3+di4)/6)
            v=max(0.,v+h*(dv1+2*dv2+2*dv3+dv4)/6)
    change=max(abs(a-b) for a,b in zip(previous,last))
    if change>1e-5: raise ValueError(f"independent reference did not reach a periodic orbit: {change}")
    return {"mean_per_input_peak":math.fsum(last)/n,"rms_per_input_peak":math.sqrt(math.fsum(x*x for x in last)/n),
            "ripple_pp_per_input_peak":max(last)-min(last),"step_s":h,"warmup_cycles":warm_cycles,
            "periodic_max_change_per_input_peak":change,"steps_per_input_cycle":n}

def expected_rectifier(config,steps_per_cycle=4000):
    c=config["circuit"];s=config["source"]
    normalized=bridge_reference(s["frequency_hz"],c["load_ohm"],c["l_h"],c["c_f"],steps_per_cycle)
    peak=math.sqrt(2)*s["rms_v"]
    return {"mean_v":peak*normalized["mean_per_input_peak"],"rms_v":peak*normalized["rms_per_input_peak"],
            "ripple_pp_v":peak*normalized["ripple_pp_per_input_peak"],"mean_load_a":peak*normalized["mean_per_input_peak"]/c["load_ohm"],
            "input_peak_v":peak,"method":"independent switched ideal-bridge LC-R ODE, fixed-step RK4 with diode nonnegative-current projection",**normalized}

def analyze_rectifier(csv_path,config):
    data=load_waveforms(Path(csv_path),COLUMNS)
    t=np.asarray(data["t_relative_s"]);ts=np.asarray(data["t_simulation_s"])
    voltage=np.asarray(data["Vdc_V"]);load=np.asarray(data["Iload_A"]);cap=np.asarray(data["Icap_A"])
    count=len(t);step=median(np.diff(t));rate=1/step;duration=count*step
    c=config["capture"];a=config["acceptance"];f=config["source"]["frequency_hz"];r=config["circuit"]["load_ohm"]
    if count<a["min_samples"]: raise ValueError("insufficient rectifier samples")
    samples_per_cycle=round(rate/f)
    if samples_per_cycle<200 or abs(rate/f-samples_per_cycle)>1e-4: raise ValueError("capture needs an integer number of samples per input cycle")
    if count%samples_per_cycle or count//samples_per_cycle<5: raise ValueError("capture does not span at least five complete input cycles")
    reference=expected_rectifier(config)
    coarse=expected_rectifier(config,2000)
    convergence=max(abs(reference[k]-coarse[k])/reference[k] for k in ("mean_v","rms_v","ripple_pp_v"))
    if convergence>.001: raise ValueError("independent reference step convergence exceeds 0.1%")
    vm=float(np.mean(voltage));vr=float(np.sqrt(np.mean(voltage**2)));ripple=float(np.ptp(voltage));im=float(np.mean(load));cm=float(np.mean(cap))
    if vm<=0 or im<=0: raise ValueError("rectifier output mean voltage and load current must be positive")
    periods=voltage.reshape(-1,samples_per_cycle)
    cycle_change=float(np.max(np.abs(np.diff(periods,axis=0)))/vm)
    cycles=[{"cycle":k+1,"mean_v":float(np.mean(v)),"ripple_pp_v":float(np.ptp(v))} for k,v in enumerate(periods)]
    spectrum=np.abs(np.fft.rfft(voltage-vm));spectrum[0]=0
    ripple_hz=float(np.fft.rfftfreq(count,d=step)[int(np.argmax(spectrum))])
    ohm_error=float(np.max(np.abs(load-voltage/r))/im)
    capacitor_balance=abs(cm)/im
    checks=[]
    def check(name,observed,expected,limit,relative=True):
        error=abs(observed-expected)/abs(expected) if relative else abs(observed-expected)
        checks.append({"name":name,"passed":bool(error<=limit+1e-12),"observed":float(observed),"expected":float(expected),"relative_error" if relative else "absolute_error":float(error),"limit":float(limit)})
    check("sample_rate_hz",rate,c["sample_rate_hz"],.01)
    check("capture_duration_s",duration,c["duration_s"],.01)
    checks.append({"name":"settled_before_capture","passed":bool(ts[0]+1e-10>=c["settle_s"]),"observed":float(ts[0]),"expected":c["settle_s"],"limit":c["settle_s"]})
    check("output_mean_v",vm,reference["mean_v"],a["relative_mean_error"])
    check("output_rms_v",vr,reference["rms_v"],a["relative_rms_error"])
    check("output_ripple_pp_v",ripple,reference["ripple_pp_v"],a["relative_ripple_error"])
    check("load_ohm_relative",ohm_error,0,a["relative_ohm_error"],False)
    check("capacitor_dc_balance_relative",capacitor_balance,0,a["relative_capacitor_balance"],False)
    check("consecutive_input_cycle_change_relative",cycle_change,0,a["relative_cycle_change"],False)
    check("dominant_ripple_hz",ripple_hz,2*f,1/duration+1e-8,False)
    signal={"Vdc_V":{"unit":"V","mean":vm,"rms":vr,"ripple_pp":ripple,"expected_mean":reference["mean_v"],"expected_rms":reference["rms_v"],"expected_ripple_pp":reference["ripple_pp_v"]},
            "Iload_A":{"unit":"A","mean":im,"expected_mean":reference["mean_load_a"],"maximum_relative_ohm_error":ohm_error},
            "Icap_A":{"unit":"A","mean":cm,"rms":float(np.sqrt(np.mean(cap**2))),"relative_dc_balance":capacitor_balance}}
    return {"schema_version":1,"model":config["model"],"backend":config["backend"],"source_csv":Path(csv_path).name,
            "status":"passed" if all(x["passed"] for x in checks) else "failed","sample_count":count,"sample_rate_hz":rate,
            "capture":{"sample_count":count,"sample_rate_hz":rate,"duration_s":duration,"cycles":count/samples_per_cycle,"samples_per_input_cycle":samples_per_cycle,"first_simulation_time_s":float(ts[0]),"last_simulation_time_s":float(ts[-1])},
            "signals":signal,"checks":checks,"reference":{**reference,"relative_coarse_fine_metric_change":convergence,
                "equations":"conducting: L di/dt=|Vs|-Vdc; C dVdc/dt=i-Vdc/R; blocked: i=0 and dVdc/dt=-Vdc/(RC)",
                "assumptions":["ideal bridge with zero forward voltage","linear series inductor","ideal output capacitor and resistor","no source resistance","periodic steady state"],
                "note":"Reference is an independent numerical calculation, not an analytical closed form or an additional Typhoon measurement."},
            "periodicity":{"dominant_ripple_hz":ripple_hz,"expected_ripple_hz":2*f,"frequency_bin_hz":1/duration,"max_consecutive_cycle_change_relative":cycle_change,"per_input_cycle":cycles},
            "analysis":{"window":"all raw captured samples, complete input cycles","filtering":"none","interpolation":"none","missing_values":"reject","rms_method":"sqrt(sum(x*x)/N)","ripple_method":"max(Vdc)-min(Vdc)","mean_method":"sum(x)/N"}}
