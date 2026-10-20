"""RLC v1 behavior and record format retained for historical replay."""
import math

class RLCAdapter:
    model_id = "rlc_filter"
    schema_version = 1
    signals = ("I", "Va1")
    columns = ("I_A", "Va1_V")
    units = {"I_A": "A", "Va1_V": "V"}
    sources = ("Vs1",)
    capture_before_start = False
    changes = []
    mapping = (("rin_ohm", "Rin", "resistance"), ("branch_r_ohm", "R", "resistance"),
               ("l_h", "L", "inductance"), ("c_f", "C", "capacitance"))

    @property
    def numeric_rules(self):
        from ..config import RLC_NUMERIC_RULES
        return RLC_NUMERIC_RULES

    setting_stages = {"source": "after_load_before_start", "circuit": "model_copy_before_compile",
                      "capture": "capture_setup", "acceptance": "analysis_only"}
    event_capabilities = {"max_per_run": 0, "targets": {}}
    @property
    def sweep_capabilities(self):
        from ..config import RLC_SWEEP_MAX_VALUES
        return {"parameter": "circuit.rin_ohm", "minimum_values": 1,
                "maximum_values": RLC_SWEEP_MAX_VALUES, "values_must_be_distinct": True}
    conditional_constraints = ["capture_complete_cycles", "min_20_samples_per_cycle",
                               "capture_samples_within_minimum_and_100000"]

    def validate(self, raw, sweep=False):
        from ..config import _validate_rlc
        return _validate_rlc(raw, sweep)

    def inspect_parameters(self, api):
        out = {}
        for key, name, prop in self.mapping:
            item = api.get_item(name)
            if item is None:
                raise ValueError(f"model is missing required component {name}")
            out[key] = float(api.get_property_value(api.prop(item, prop)))
        return out

    def prepare(self, api, config):
        for key, name, prop in self.mapping:
            item = api.get_item(name)
            if item is None:
                raise ValueError(f"required component {name} was not found")
            api.set_property_value(api.prop(item, prop), str(config["circuit"][key]))
        actual = self.inspect_parameters(api)
        for key, value in actual.items():
            if not math.isclose(value, config["circuit"][key], rel_tol=1e-12):
                raise ValueError(f"model read-back mismatch for {key}")
        return actual

    def initialize(self, hil, config):
        from ..runtime import require
        s = config["source"]
        require(hil.set_source_sine_waveform("Vs1", rms=s["rms_v"], frequency=s["frequency_hz"],
                    phase=s["phase_deg"], harmonics_pu=()), "set sine source")
        settings = hil.get_source_settings("Vs1")
        for key, expected in (("rms", s["rms_v"]), ("frequency", s["frequency_hz"]), ("phase", s["phase_deg"])):
            if settings is None or not math.isclose(float(settings[key]), expected, rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError(f"source read-back mismatch for {key}")
        return {"actual_source_settings": settings}

    def schedule(self, hil, config):
        return []

    def check_sampling(self, rate, count, config):
        f = config["source"]["frequency_hz"]
        if rate < 20*f:
            raise ValueError("actual capture sampling falls outside validated teaching limits")
        if not math.isclose(count/rate*f, round(count/rate*f), abs_tol=1e-5):
            raise ValueError("quantized sampling would not capture complete source cycles")

    def analyze(self, path, config):
        from ..analysis import analyze_rlc
        return analyze_rlc(path, config)

    def report(self, path, manifest):
        from ..reporting import _write_rlc_report
        return _write_rlc_report(path, manifest)
