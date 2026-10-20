"""Official single phase bridge: source -> L -> bridge -> (C || R)."""
from copy import deepcopy
import math
from ..config import number

class RectifierAdapter:
    model_id = "single_phase_rectifier"
    schema_version = 1
    has_events = False
    signals = ("Va2", "Iload1", "Icdc1")
    columns = ("Vdc_V", "Iload_A", "Icap_A")
    units = {"Vdc_V": "V", "Iload_A": "A", "Icap_A": "A"}
    sources = ("Va1",)
    capture_before_start = False
    changes = ["Set L, C and load R in the per-run copy; disable Va2's original 2 Hz measurement low-pass so captured voltage preserves physical ripple."]
    mapping = (("load_ohm", "Rload1", "resistance"), ("l_h", "La1", "inductance"), ("c_f", "Cdc1", "capacitance"))

    numeric_rules = {
        "source": {"rms_v": (10, 400), "frequency_hz": (40, 60), "phase_deg": (-360, 360)},
        "circuit": {"load_ohm": (25, 200), "l_h": (.0005, .002), "c_f": (.0005, .002)},
        "capture": {"settle_s": (.5, 10), "duration_s": (.1, 2),
                    "sample_rate_hz": (10000, 100000), "wall_timeout_s": (30, 300)},
        "acceptance": {"relative_mean_error": (.0001, .02), "relative_rms_error": (.0001, .02),
                       "relative_ripple_error": (.0001, .05), "relative_ohm_error": (.0001, .005),
                       "relative_capacitor_balance": (.0001, .01), "relative_cycle_change": (.0001, .005),
                       "min_samples": (256, 100000)},
    }
    setting_stages = {"source": "after_load_before_start", "circuit": "model_copy_before_compile",
                      "capture": "capture_setup", "acceptance": "analysis_only"}
    event_capabilities = {"max_per_run": 0, "targets": {}}
    conditional_constraints = ["capture_complete_cycles", "min_200_samples_per_cycle",
                               "integer_samples_per_cycle", "settle_at_least_12_rc_or_0_5_s",
                               "capture_samples_within_minimum_and_100000"]

    def validate(self, raw, sweep=False):
        if sweep:
            raise ValueError("rectifier uses separate fixed configurations; sweep is RLC-only")
        c=deepcopy(raw)
        keys={"schema_version","model","backend","source","circuit","capture","acceptance"}
        if not isinstance(c,dict) or set(c)!=keys:
            raise ValueError(f"configuration keys must be exactly {sorted(keys)}")
        if type(c["schema_version"]) is not int or c["schema_version"]!=1:
            raise ValueError("rectifier steady-state configuration schema_version must be 1")
        if c["model"]!=self.model_id or c["backend"]!="virtual_hil":
            raise ValueError("rectifier requires single_phase_rectifier on virtual_hil")
        for group,limits in self.numeric_rules.items():
            if not isinstance(c[group],dict) or set(c[group])!=set(limits):
                raise ValueError(f"{group} keys must be exactly {sorted(limits)}")
            for key,(low,high) in limits.items():
                c[group][key]=number(c[group][key],f"{group}.{key}",low,high)
        minimum=c["acceptance"]["min_samples"]
        if not minimum.is_integer(): raise ValueError("min_samples must be an integer")
        c["acceptance"]["min_samples"]=int(minimum)
        cap=c["capture"];f=c["source"]["frequency_hz"]
        cycles=cap["duration_s"]*f
        if cycles<5 or not math.isclose(cycles,round(cycles),abs_tol=1e-8):
            raise ValueError("capture must span at least five complete input cycles")
        samples=cap["duration_s"]*cap["sample_rate_hz"]
        if not minimum<=samples<=100000: raise ValueError("capture sample count is outside limits")
        if cap["sample_rate_hz"]<200*f: raise ValueError("rectifier requires 200 samples per input cycle")
        required=max(.5,12*c["circuit"]["load_ohm"]*c["circuit"]["c_f"])
        if cap["settle_s"]+1e-12<required: raise ValueError(f"settle_s must be at least {required:g} (12 R C or 0.5 s)")
        return c

    def inspect_parameters(self,api):
        out={}
        for key,name,prop in self.mapping:
            item=api.get_item(name)
            if item is None: raise ValueError(f"required component {name} missing")
            out[key]=float(api.get_property_value(api.prop(item,prop)))
        measurement=api.get_item("Va2")
        if measurement is None: raise ValueError("Va2 measurement missing")
        out["voltage_measurement_bw_limit"]=str(api.get_property_value(api.prop(measurement,"bw_limit")))
        out["voltage_measurement_frequency_hz"]=float(api.get_property_value(api.prop(measurement,"frequency")))
        return out

    def prepare(self,api,config):
        for key,name,prop in self.mapping:
            item=api.get_item(name)
            if item is None: raise ValueError(f"required component {name} missing")
            api.set_property_value(api.prop(item,prop),str(config["circuit"][key]))
        measurement=api.get_item("Va2")
        if measurement is None: raise ValueError("Va2 measurement missing")
        api.set_property_value(api.prop(measurement,"bw_limit"),"False")
        out=self.inspect_parameters(api)
        for key,_,_ in self.mapping:
            if not math.isclose(out[key],config["circuit"][key],rel_tol=1e-12): raise ValueError(f"model read-back differs: {key}")
        if out["voltage_measurement_bw_limit"].lower()!="false": raise ValueError("Va2 low-pass could not be disabled")
        return out

    def initialize(self,hil,config):
        from ..runtime import require
        s=config["source"]
        require(hil.set_source_sine_waveform("Va1",rms=s["rms_v"],frequency=s["frequency_hz"],phase=s["phase_deg"],harmonics_pu=()),"set rectifier sine source")
        actual=hil.get_source_settings("Va1")
        for key,expected in (("rms",s["rms_v"]),("frequency",s["frequency_hz"]),("phase",s["phase_deg"])):
            if actual is None or not math.isclose(float(actual[key]),expected,rel_tol=1e-10,abs_tol=1e-10): raise ValueError(f"source read-back mismatch: {key}")
        return {"actual_source_settings":actual}

    def schedule(self,hil,config): return []

    def check_sampling(self,rate,count,config):
        f=config["source"]["frequency_hz"]
        if rate<200*f or not math.isclose(count/rate*f,round(count/rate*f),abs_tol=1e-5):
            raise ValueError("quantized rectifier capture must span complete cycles at >=200 samples/cycle")
        if not math.isclose(rate/f,round(rate/f),abs_tol=1e-5):
            raise ValueError("rectifier periodic comparison requires integer samples per source cycle")

    def analyze(self,path,config):
        from ..rectifier_analysis import analyze_rectifier
        return analyze_rectifier(path,config)

    def report(self,path,manifest):
        from ..rectifier_reporting import write_rectifier_report
        return write_rectifier_report(path,manifest)
