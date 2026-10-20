"""Official Boost plant plus an in-model reference event and observer signals."""
from copy import deepcopy
import math
import re
from pathlib import Path

CONTROL_PERIOD_S = 100e-6

class BoostAdapter:
    has_events = True
    model_id = "boost_closed_loop"
    schema_version = 2
    signals = ("Vout", "Iin", "ReferenceApplied", "VinMeasured")
    columns = ("Vout_V", "Iin_A", "ReferenceApplied_V", "VinMeasured_V")
    units = dict(zip(columns, ("V", "A", "V", "V")))
    sources = ("Vin",)
    capture_before_start = True
    changes = ["Insert LabReferenceStep and LabReferenceSum between Reference and Sum1.in; arm Step one control tick early to compensate the added Sum stage",
               "Observe summed reference with ReferenceApplied probe",
               "Observe voltage across Vin using VinMeasured",
               "Keep official plant and PI values; keep additional Load open"]

    numeric_rules = {
        "parameters": {"input_voltage_v": (.01, 1000), "reference_voltage_v": (.01, 100)},
        "capture": {"start_s": (0, 0), "duration_s": (.2, 5),
                    "sample_rate_hz": (10000, 200000), "wall_timeout_s": (10, 300)},
        "acceptance": {"steady_state_relative_error": (.0001, .2), "pre_event_relative_error": (.0001, .2),
                       "settling_band_relative": (.0001, .2), "max_settling_time_s": (.001, 4),
                       "max_overshoot_fraction": (0, 1), "max_deviation_relative": (0, 1),
                       "steady_window_s": (.001, 1), "pre_event_window_s": (.001, 1),
                       "min_samples": (256, 100000)},
    }
    fixed_fields = {"parameters.pwm_enabled": {"type": "boolean", "allowed_values": [True],
                                              "setting_stage": "after_load_before_start"}}
    field_dependencies = {"parameters.reference_voltage_v": {
        "also_used_during": "model_copy_before_compile", "when": "reference_event"}}
    setting_stages = {"parameters": "after_load_before_start", "capture": "capture_setup",
                      "acceptance": "analysis_only"}
    event_capabilities = {"max_per_run": 1, "targets": {
        "reference_voltage_v": {"value_minimum": .01, "value_maximum": 100,
                                "setting_stage": "model_copy_before_compile"},
        "input_voltage_v": {"value_minimum": .01, "value_maximum": 1000,
                            "setting_stage": "scheduled_source_change"}},
        "time_unit": "s", "time_quantum_s": CONTROL_PERIOD_S,
        "time_minimum_ref": "acceptance.pre_event_window_s",
        "time_maximum_ref": "capture.duration_s",
        "recovery_window_required": True}
    conditional_constraints = ["reference_above_input_before_and_after_event",
                               "event_changes_value", "event_time_within_capture_and_recovery_window",
                               "capture_even_integer_samples_within_minimum_and_100000"]

    def validate(self, raw, sweep=False):
        from ..config import number
        c = deepcopy(raw)
        keys = {"schema_version", "model", "backend", "parameters", "events", "capture", "acceptance"}
        if sweep:
            raise ValueError("Boost v2 uses independent run configs; sweep remains the RLC Rin experiment")
        if not isinstance(c, dict) or set(c) != keys:
            raise ValueError(f"Boost configuration keys must be exactly {sorted(keys)}")
        if type(c["schema_version"]) is not int or c["schema_version"] != 2 or c["backend"] != "virtual_hil":
            raise ValueError("Boost requires schema_version 2 and virtual_hil")
        p = c["parameters"]
        if not isinstance(p, dict) or set(p) != {"input_voltage_v", "reference_voltage_v", "pwm_enabled"}:
            raise ValueError("parameters require input_voltage_v, reference_voltage_v, pwm_enabled")
        p["input_voltage_v"] = number(p["input_voltage_v"], "input_voltage_v", *self.numeric_rules["parameters"]["input_voltage_v"])
        p["reference_voltage_v"] = number(p["reference_voltage_v"], "reference_voltage_v", *self.numeric_rules["parameters"]["reference_voltage_v"])
        if p["pwm_enabled"] is not True:
            raise ValueError("closed-loop teaching experiments require pwm_enabled=true")
        for group in ("capture", "acceptance"):
            fields = self.numeric_rules[group]
            if not isinstance(c[group], dict) or set(c[group]) != set(fields):
                raise ValueError(f"{group} keys must be exactly {sorted(fields)}")
            for key, bounds in fields.items():
                c[group][key] = number(c[group][key], f"{group}.{key}", *bounds)
        a, cap = c["acceptance"], c["capture"]
        if not a["min_samples"].is_integer():
            raise ValueError("acceptance.min_samples must be an integer")
        a["min_samples"] = int(a["min_samples"])
        n = cap["duration_s"]*cap["sample_rate_hz"]
        if not math.isclose(n, round(n), abs_tol=1e-7) or int(round(n)) % 2 or not a["min_samples"] <= n <= 100000:
            raise ValueError("capture requires an even integer sample count within min_samples..100000")
        if a["steady_window_s"] >= cap["duration_s"]:
            raise ValueError("steady-state window must be shorter than capture")
        if not isinstance(c["events"], list) or len(c["events"]) > 1:
            raise ValueError("Boost v2 supports zero or one event per run")
        ref, vin = p["reference_voltage_v"], p["input_voltage_v"]
        if ref <= vin:
            raise ValueError("Boost reference voltage must exceed input voltage")
        for event in c["events"]:
            if not isinstance(event, dict) or set(event) != {"at_s", "target", "value"}:
                raise ValueError("event requires at_s, target, value")
            target = event["target"]
            if target not in self.event_capabilities["targets"]:
                raise ValueError("unsupported event target")
            event["at_s"] = number(event["at_s"], "event.at_s", a["pre_event_window_s"], cap["duration_s"])
            ticks = event["at_s"]/CONTROL_PERIOD_S
            if not math.isclose(ticks, round(ticks), rel_tol=0, abs_tol=1e-7):
                raise ValueError("event.at_s must align to the 100 us control period")
            if event["at_s"] + a["max_settling_time_s"] + a["steady_window_s"] > cap["duration_s"] + 1e-10:
                raise ValueError("capture must include the event, recovery allowance and final steady window")
            bounds = self.event_capabilities["targets"][target]
            event["value"] = number(event["value"], "event.value", bounds["value_minimum"], bounds["value_maximum"])
            if event["value"] == p[target]:
                raise ValueError("event must change its target value")
            if target == "reference_voltage_v":
                ref = event["value"]
            else:
                vin = event["value"]
            if ref <= vin:
                raise ValueError("post-event Boost reference must exceed input voltage")
        return c

    def inspect_parameters(self, api):
        mapping = {"l_h": ("L", "inductance"), "c_f": ("C", "capacitance"),
                   "load_ohm": ("R1", "resistance"), "additional_load_ohm": ("R2", "resistance"),
                   "inductor_resistance_ohm": ("RL", "resistance"), "capacitor_esr_ohm": ("ESR", "resistance")}
        values = {key: float(api.get_property_value(api.prop(api.get_item(name), prop)))
                  for key, (name, prop) in mapping.items()}
        # THCC load does not execute the model initialization namespace. Read
        # its four literal assignments without executing arbitrary model code.
        text = Path(api.get_model_file_path()).read_text(encoding="utf-8")
        controller = {}
        for key, var in (("kp", "P"), ("ki", "I"), ("integrator_initial", "I_initial"), ("period_s", "Ts")):
            matches = re.findall(r"(?m)^\s*"+var+r"\s*=\s*([+\-0-9.eE]+)\s*$", text)
            if len(matches) != 1:
                raise ValueError(f"expected one literal model initialization assignment for {var}")
            controller[key] = float(matches[0])
        values["controller"] = controller
        values["controller_value_source"] = "literal assignments in saved model initialization; schematic load does not execute this code"
        pi = api.get_item("PID controller")
        values["controller_expressions"] = {key: api.get_property_value(api.prop(pi, key)) for key in ("kp", "ki", "int_init_value")}
        if values["controller_expressions"] != {"kp": "P", "ki": "I", "int_init_value": "I_initial"}:
            raise ValueError("official PI parameter expressions differ from the validated model")
        values["additional_load_initial_state"] = api.get_property_value(api.prop(api.get_item("Load"), "initial_state"))
        return values

    def prepare(self, api, config):
        actual = self.inspect_parameters(api)
        if not math.isclose(actual["controller"]["period_s"], CONTROL_PERIOD_S, rel_tol=1e-10):
            raise ValueError("official control period differs from the validated 100 us")
        ref, error_sum = api.get_item("Reference"), api.get_item("Sum1")
        connections = api.find_connections(api.term(ref, "out"), api.term(error_sum, "in"))
        if len(connections) != 1:
            raise ValueError("expected exactly one Reference -> Sum1.in connection")
        api.delete_item(connections[0])
        step = api.create_component("core/Step", name="LabReferenceStep", position=(1760, 2040))
        adder = api.create_component("core/Sum", name="LabReferenceSum", position=(1944, 2100))
        probe = api.create_component("core/Probe", name="ReferenceApplied", position=(1944, 2024))
        event = config["events"][0] if config["events"] else None
        at = (round(event["at_s"]/CONTROL_PERIOD_S)-1)*CONTROL_PERIOD_S if event and event["target"] == "reference_voltage_v" else .5
        delta = event["value"]-config["parameters"]["reference_voltage_v"] if event and event["target"] == "reference_voltage_v" else 0
        api.set_property_values(step, {"step_time": str(at), "initial_value": "0", "final_value": str(delta), "execution_rate": "Ts"})
        api.set_property_values(adder, {"signs": "++", "execution_rate": "Ts"})
        api.set_property_value(api.prop(probe, "execution_rate"), "Ts")
        api.create_connection(api.term(ref, "out"), api.term(adder, "in"))
        api.create_connection(api.term(step, "out"), api.term(adder, "in1"))
        api.create_connection(api.term(adder, "out"), api.term(error_sum, "in"))
        api.create_connection(api.term(adder, "out"), api.term(probe, "in"))
        sensor = api.create_component("core/Voltage Measurement", name="VinMeasured", position=(1456, 1936), rotation="right")
        source = api.get_item("Vin")
        api.create_connection(api.term(source, "p_node"), api.term(sensor, "p_node"))
        api.create_connection(api.term(source, "n_node"), api.term(sensor, "n_node"))
        api.set_property_value(api.prop(api.get_item("Load"), "initial_state"), "off")
        read_back = api.get_property_values(step)
        for key, expected in (("step_time", at), ("initial_value", 0), ("final_value", delta)):
            value = read_back[key]
            value = value[0] if isinstance(value, (list, tuple)) else value
            if not math.isclose(float(value), expected, rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError(f"reference Step read-back mismatch: {key}")
        actual["reference_step"] = {"at_s": at, "delta_v": delta, "period_s": CONTROL_PERIOD_S,
                                     "sum_pipeline_compensation_s": CONTROL_PERIOD_S if delta else 0,
                                     "properties_read_back": read_back}
        return actual

    def initialize(self, hil, config):
        from ..runtime import require
        p = config["parameters"]
        for name, value in (("PWM Enable", 1.0), ("Reference", p["reference_voltage_v"])):
            require(hil.set_scada_input_value(name, value), f"set {name}")
            settings = hil.get_scada_input_settings(name)
            if not settings or not math.isclose(float(settings["input_value"]), value, abs_tol=1e-8):
                raise ValueError(f"SCADA read-back mismatch for {name}")
        require(hil.set_source_constant_value("Vin", value=p["input_voltage_v"]), "set input voltage")
        settings = hil.get_source_settings("Vin")
        if not settings or not math.isclose(float(settings["value"]), p["input_voltage_v"], abs_tol=1e-8):
            raise ValueError("source read-back mismatch for Vin")
        require(hil.set_contactor("Load", swControl=True, swState=False), "open additional load")
        load = hil.get_contactor_settings("Load")
        if not load or load.get("software_control_enabled") is not True or load.get("software_value") != "Opened":
            raise ValueError("additional load read-back mismatch")
        return {"actual_source_settings": settings, "actual_scada_settings":
                {name: hil.get_scada_input_settings(name) for name in ("PWM Enable", "Reference")}, "actual_load_settings": load}

    def describe_schedule(self, config):
        result = []
        for e in config["events"]:
            scheduled = round(e["at_s"]/CONTROL_PERIOD_S)*CONTROL_PERIOD_S
            ref_event = e["target"] == "reference_voltage_v"
            result.append({**e, "scheduled_at_s": scheduled,
                           "mechanism": "model_step" if ref_event else "source_executeAt",
                           "model_step_trigger_at_s": (round(e["at_s"]/CONTROL_PERIOD_S)-1)*CONTROL_PERIOD_S if ref_event else None,
                           "pipeline_compensation_s": CONTROL_PERIOD_S if ref_event else 0})
        return result

    def schedule(self, hil, config):
        from ..runtime import require
        for e in config["events"]:
            if e["target"] == "input_voltage_v":
                require(hil.set_source_constant_value("Vin", value=e["value"], executeAt=e["at_s"]), "schedule input disturbance")
        return self.describe_schedule(config)

    def check_sampling(self, rate, count, config):
        if rate < 10000 or not math.isclose(rate, config["capture"]["sample_rate_hz"], rel_tol=.01):
            raise ValueError("actual Boost sampling must be >=10 kHz and match request within 1%")

    def analyze(self, path, config):
        from ..boost_analysis import analyze
        return analyze(path, config)

    def report(self, path, manifest):
        from ..boost_reporting import write_report
        return write_report(path, manifest)
