"""Explicit code-owned adapters. Case metadata never imports Python code."""
from importlib import import_module
from copy import deepcopy

ADAPTERS = {
    "rlc_filter": (".rlc", "RLCAdapter"),
    "boost_closed_loop": (".boost", "BoostAdapter"),
    "single_phase_rectifier": (".rectifier", "RectifierAdapter"),
    "induction_motor_closed_loop": (".induction", "InductionMotorAdapter"),
}


def supported_models():
    return tuple(ADAPTERS)


def records_events(adapter, config):
    predicate = getattr(adapter, 'record_events', None)
    return bool(predicate(config) if predicate else getattr(adapter, 'has_events', False))


def get_adapter(model_id):
    if model_id not in ADAPTERS:
        raise ValueError(f"unsupported model: {model_id!r}")
    module, name = ADAPTERS[model_id]
    return getattr(import_module(module, __name__), name)()


def _unit(name):
    for suffix, unit in (("_ohm", "ohm"), ("_hz", "Hz"), ("_rpm", "rpm"),
                         ("_deg", "deg"), ("_pu", "pu"), ("_samples", "count"),
                         ("_s", "s"), ("_v", "V"), ("_h", "H"), ("_f", "F")):
        if name.endswith(suffix):
            return unit
    return None


def describe_capabilities(adapter):
    """Static, serializable support contract; actual configs still use validate()."""
    from ..versions import analysis_method_version
    operations = ("prepare", "initialize", "schedule", "check_sampling", "analyze", "report")
    method_version = analysis_method_version("run", adapter.model_id)
    fields = {}
    for group, rules in adapter.numeric_rules.items():
        stage = adapter.setting_stages[group]
        fields[group] = {
            name: {"type": "integer" if name == "min_samples" else "number",
                   "unit": _unit(name), "minimum": bounds[0], "maximum": bounds[1],
                   "setting_stage": stage, "limit_source": "current_validated_scope"}
            for name, bounds in rules.items()
        }
    for name, bounds in getattr(adapter, "event_acceptance_rules", {}).items():
        fields["acceptance"][name] = {
            "type": "number", "unit": _unit(name), "minimum": bounds[0], "maximum": bounds[1],
            "setting_stage": "analysis_only", "limit_source": "current_validated_scope",
            "when": "events_nonempty",
        }
    for path, spec in getattr(adapter, "fixed_fields", {}).items():
        group, name = path.split(".", 1)
        fields[group][name] = deepcopy(spec)
    for path, dependency in getattr(adapter, "field_dependencies", {}).items():
        group, name = path.split(".", 1)
        fields[group][name]["dependency"] = deepcopy(dependency)
    events = deepcopy(adapter.event_capabilities)
    for target, spec in events["targets"].items():
        spec.update(type="number", unit=_unit(target), limit_source="current_validated_scope")
    if events["max_per_run"]:
        events["time_quantum_source"] = "model_control_period"
    return {
        "configuration_schema_version": adapter.schema_version,
        "analysis_method_version": method_version,
        "run": method_version is not None and all(callable(getattr(adapter, method, None)) for method in operations),
        "runtime_events": bool(getattr(adapter, "has_events", False)),
        "capture_signals": list(adapter.signals),
        "signal_details": [
            {"api_name": signal, "column": column, "unit": adapter.units[column]}
            for signal, column in zip(adapter.signals, adapter.columns)
        ],
        "configuration_fields": fields,
        "events": events,
        "sweep": deepcopy(getattr(adapter, "sweep_capabilities", None)),
        "conditional_constraints": list(adapter.conditional_constraints),
    }
