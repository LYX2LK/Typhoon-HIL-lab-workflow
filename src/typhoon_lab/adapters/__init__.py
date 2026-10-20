"""Explicit code-owned adapters. Case metadata never imports Python code."""
from importlib import import_module

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
