"""Independent versions for saved records and deterministic analysis methods."""

RECORD_FORMAT_VERSION = 1
ANALYSIS_METHOD_VERSIONS = {
    ("run", "generic_pv_plant"): 2,
    ("run", "rlc_filter"): 1,
    ("run", "single_phase_rectifier"): 1,
    ("run", "boost_closed_loop"): 1,
    ("run", "induction_motor_closed_loop"): 1,
    ("sweep", "rlc_filter"): 1,
    ("comparison", "single_phase_rectifier"): 1,
    ("modeling_practice", "self_built_rlc"): 1,
    ("case", None): 1,
    ("smoke", None): 1,
}


def analysis_method_version(kind, model=None):
    """Method revisions are scoped to a result kind and model."""
    return ANALYSIS_METHOD_VERSIONS.get((kind, model), ANALYSIS_METHOD_VERSIONS.get((kind, None)))


def require_analysis_method_version(kind, model=None):
    version = analysis_method_version(kind, model)
    if version is None:
        raise ValueError(f"analysis method version is not registered for {kind}/{model}")
    return version


def record_version_problems(manifest):
    """Accept pre-versioned records while rejecting unknown new formats."""
    problems = []
    record_version = manifest.get("record_format_version")
    if record_version is not None and type(record_version) is not int:
        problems.append("record_format_version must be an integer")
    elif record_version not in (None, RECORD_FORMAT_VERSION):
        problems.append(f"unsupported record_format_version: {record_version}")
    method_version = manifest.get("analysis_method_version")
    if method_version is not None and type(method_version) is not int:
        problems.append("analysis_method_version must be an integer")
    elif method_version is not None:
        current = analysis_method_version(manifest.get("kind"), manifest.get("model"))
        if current is None or method_version != current:
            problems.append(f"unsupported analysis_method_version: {method_version}")
    return problems
