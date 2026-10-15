"""Explicit, versioned model adapters; no automatic arbitrary-model execution."""

def get_adapter(model_id):
    if model_id == "rlc_filter":
        from .rlc import RLCAdapter
        return RLCAdapter()
    if model_id == "boost_closed_loop":
        from .boost import BoostAdapter
        return BoostAdapter()
    raise ValueError(f"unsupported model: {model_id!r}")
